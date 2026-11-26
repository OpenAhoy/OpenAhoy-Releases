// A validated session contains authorized source paths and integer edit points.
#include <filesystem>
#include <memory>
#include <numeric>
#include <set>

namespace bus {
namespace fs = std::filesystem;
using Frame = SInt64;

bool number(id object) {
    return [object isKindOfClass:NSNumber.class] &&
           CFGetTypeID((__bridge CFTypeRef)object) != CFBooleanGetTypeID();
}
Frame integer(id value, Frame low, Frame high, const char* label) {
    require(number(value), label);
    double d=[value doubleValue];
    require(std::isfinite(d) && std::floor(d)==d && d>=double(low) && d<=double(high),label);
    return static_cast<Frame>(d);
}
float scalar(NSDictionary* fields, NSString* key, float fallback, float lo, float hi) {
    id value=fields[key]; if (!value) return fallback;
    require(number(value),"expected a finite gain or balance");
    const double v=[value doubleValue]; require(std::isfinite(v) && v>=lo && v<=hi,"gain or balance outside supported range");
    return float(v);
}
bool flag(NSDictionary* fields, NSString* key) {
    id value=fields[key]; if (!value) return false;
    require(CFGetTypeID((__bridge CFTypeRef)value)==CFBooleanGetTypeID(),"expected a boolean");
    return [value boolValue];
}
std::string textField(NSDictionary* d, NSString* key) {
    id value=d[key]; require([value isKindOfClass:NSString.class] && [value length]>0,"missing string");
    const char* text=[value UTF8String]; require(text && strlen(text)==[value lengthOfBytesUsingEncoding:NSUTF8StringEncoding],"invalid string");
    return text;
}
void fields(NSDictionary* dict, NSArray<NSString*>* allowed) {
    require([dict isKindOfClass:NSDictionary.class],"expected object");
    for (id key in dict) require([allowed containsObject:key],"unknown manifest field");
}
NSDictionary* readJSON(NSURL* url) {
    NSNumber* size=nil;
    require([url getResourceValue:&size forKey:NSURLFileSizeKey error:nil] && size.unsignedLongLongValue<=16*1024*1024,
            "manifest unavailable or too large");
    NSData* bytes=[NSData dataWithContentsOfURL:url]; require(bytes,"cannot read manifest");
    id obj=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
    require([obj isKindOfClass:NSDictionary.class],"expected JSON object");
    return obj;
}
struct Identity {
    dev_t dev; ino_t inode; off_t size; timespec mtime, ctime;
    static Identity read(const fs::path& path) {
        struct stat s{}; require(lstat(path.c_str(),&s)==0 && S_ISREG(s.st_mode),"source is not a regular file");
        return {s.st_dev,s.st_ino,s.st_size,s.st_mtimespec,s.st_ctimespec};
    }
    bool operator==(const Identity& o) const {
        return dev==o.dev && inode==o.inode && size==o.size && mtime.tv_sec==o.mtime.tv_sec &&
            mtime.tv_nsec==o.mtime.tv_nsec && ctime.tv_sec==o.ctime.tv_sec && ctime.tv_nsec==o.ctime.tv_nsec;
    }
};
struct Clip {
    Frame at, source, count, fadeIn, fadeOut;
    float gain;
};
struct Track {
    fs::path path;
    Identity identity;
    std::vector<Clip> clips;
    UInt32 channels;
    double sourceRate;
    float gainL, gainR, positiveScale;
    bool mute;
    size_t next=0;
    void verify() const {
        require(fs::canonical(path)==path && Identity::read(path)==identity,"source changed during session");
    }
};
struct Voice {
    Track* track;
    const Clip* clip;
    AudioFile file;
    Voice(Track& t,const Clip& c,double rate,Frame skipped):track(&t),clip(&c) {
        t.verify();
        checked(ExtAudioFileOpenURL((__bridge CFURLRef)urlFor(t.path.c_str()),&file.ref),"open source voice");
        file.clientFormat(format(rate,t.channels,true));
        // Preserve the rational SRC phase on transport seek. Opening at the nearest
        // source sample would otherwise permanently shift a high-frequency signal.
        Frame anchor=skipped;
        if (t.sourceRate!=rate) {
            anchor=0;
            if (std::floor(t.sourceRate)==t.sourceRate) {
                const Frame period=Frame(rate)/std::gcd(Frame(rate),Frame(t.sourceRate));
                anchor=(skipped/period)*period;
            }
        }
        const Frame cursor=c.source+Frame(std::llround(anchor*t.sourceRate/rate));
        checked(ExtAudioFileSeek(file.ref,cursor),"seek source clip");
        Block discard;
        while(anchor<skipped) {
            const UInt32 wanted=UInt32(std::min<Frame>(blockSize,skipped-anchor));
            UInt32 read=wanted;auto buf=discard.buffers(t.channels,wanted);
            checked(ExtAudioFileRead(file.ref,&read,buf.ptr()),"prime source converter");
            require(read==wanted,"short source during converter priming");anchor+=read;
        }
    }
};
struct Arrangement {
    UInt32 rate;
    Frame length;
    std::vector<Track> tracks;
    std::vector<std::unique_ptr<Voice>> voices;
    explicit Arrangement(NSDictionary* d) {
        fields(d,@[@"schema",@"sampleRate",@"frames",@"mediaRoot",@"tracks"]);
        require(integer(d[@"schema"],1,1,"unsupported schema")==1,"unsupported schema");
        rate=UInt32(integer(d[@"sampleRate"],44100,192000,"invalid session rate"));
        const std::set<UInt32> rates{44100,48000,88200,96000,176400,192000};
        require(rates.count(rate),"unsupported session rate");
        length=integer(d[@"frames"],1,Frame(rate)*86400,"invalid session frame count");
        fs::path root(textField(d,@"mediaRoot"));
        require(root.is_absolute() && fs::canonical(root)==root && fs::is_directory(root),"mediaRoot must be a canonical absolute directory");
        NSArray* rows=d[@"tracks"]; require([rows isKindOfClass:NSArray.class] && rows.count && rows.count<=1024,"invalid tracks");
        std::set<std::string> ids;
        for (NSDictionary* row in rows) {
            fields(row,@[@"id",@"file",@"gain",@"pan",@"mute",@"clips"]);
            require(ids.insert(textField(row,@"id")).second,"duplicate track ID");
            const fs::path relative(textField(row,@"file"));
            require(relative.is_relative(),"source must be relative");
            for(const auto& piece:relative) require(piece!=".." && piece!="." && !piece.empty(),"invalid source path");
            const auto path=root/relative;
            require(fs::canonical(path)==path,"linked or missing source path");
            AudioFile input;
            const auto identity=Identity::read(path);
            checked(ExtAudioFileOpenURL((__bridge CFURLRef)urlFor(path.c_str()),&input.ref),"open source");
            auto info=input.get<AudioStreamBasicDescription>(kExtAudioFileProperty_FileDataFormat);
            auto total=input.get<Frame>(kExtAudioFileProperty_FileLengthFrames);
            require(info.mChannelsPerFrame==1 || info.mChannelsPerFrame==2,"expected mono/stereo source");
            require(total>0 && std::isfinite(info.mSampleRate) && info.mSampleRate>=8000,"invalid source rate/length");
            const float gain=scalar(row,@"gain",1,0,64), pan=scalar(row,@"pan",0,-1,1);
            const float atten=std::abs(pan)==1 ? 0.f : std::cos(std::abs(pan)*float(std::numbers::pi/2));
            const bool signedPCM=info.mFormatID==kAudioFormatLinearPCM && (info.mFormatFlags&kAudioFormatFlagIsSignedInteger);
            // Match the existing Studio decoder's signed-PCM endpoint mapping at unity sample rate.
            const float scale=signedPCM && info.mBitsPerChannel>=8 && info.mBitsPerChannel<=32 &&
                info.mSampleRate==rate ? float(std::ldexp(1.,info.mBitsPerChannel-1)/
                (std::ldexp(1.,info.mBitsPerChannel-1)-1)) : 1.f;
            Track track{path,identity,{},info.mChannelsPerFrame,info.mSampleRate,
                gain*(pan>0?atten:1),gain*(pan<0?atten:1),scale,flag(row,@"mute")};
            NSArray* clips=row[@"clips"];require([clips isKindOfClass:NSArray.class] && clips.count<=100000,"invalid clips");
            for (NSDictionary* v in clips) {
                fields(v,@[@"start",@"sourceStart",@"frames",@"gain",@"fadeIn",@"fadeOut"]);
                const Frame start=integer(v[@"start"],0,length,"invalid clip start");
                const Frame count=integer(v[@"frames"],1,length-start,"clip exceeds arrangement");
                const Frame source=integer(v[@"sourceStart"],0,total-1,"invalid source start");
                require(count<=Frame(std::llround((total-source)*double(rate)/info.mSampleRate)), "clip exceeds source length");
                const Frame in=v[@"fadeIn"]?integer(v[@"fadeIn"],0,count,"invalid fade in"):0;
                const Frame out=v[@"fadeOut"]?integer(v[@"fadeOut"],0,count,"invalid fade out"):0;
                track.clips.push_back({start,source,count,in,out,scalar(v,@"gain",1,0,64)});
            }
            std::stable_sort(track.clips.begin(),track.clips.end(),[](auto& a,auto& b){return a.at<b.at;});
            tracks.emplace_back(std::move(track));
        }
    }
    void reset() {
        voices.clear();
        for(auto& t:tracks) { t.verify();t.next=0; }
    }
    void mix(Frame at,UInt32 n,Block& out) {
        for(auto& ch:out.samples) std::fill_n(ch.data(),n,0.f);
        for(auto& t:tracks) {
            while(t.next<t.clips.size() && t.clips[t.next].at<at+n) {
                const auto& clip=t.clips[t.next++];
                if(clip.at+clip.count>at && !t.mute && (t.gainL!=0 || t.gainR!=0) && clip.gain!=0)
                    voices.emplace_back(std::make_unique<Voice>(t,clip,rate,std::max<Frame>(0,at-clip.at)));
            }
        }
        // Keep manifest track order even when a later clip enters a long-running mix.
        std::stable_sort(voices.begin(),voices.end(),[](const auto& a,const auto& b) {
            return a->track!=b->track ? a->track < b->track : a->clip < b->clip;
        });
        Block input;
        for(auto& v:voices) {
            const auto& t=*v->track;
            const auto& c=*v->clip;
            const auto begin=std::max(at,c.at),end=std::min<Frame>(at+n,c.at+c.count);
            if(end<=begin) continue;
            UInt32 expected=UInt32(end-begin),got=expected;
            auto buf=input.buffers(t.channels,expected);
            checked(ExtAudioFileRead(v->file.ref,&got,buf.ptr()),"read source voice");
            require(got==expected,"source decoder returned fewer frames than the clip requires");
            for(UInt32 i=0;i<got;++i) {
                const auto k=begin+i-c.at;
                float fade=c.gain;
                if(c.fadeIn && k<c.fadeIn) fade*=float(k)/float(c.fadeIn);
                if(c.fadeOut && c.count-1-k<c.fadeOut) fade*=float(c.count-1-k)/float(c.fadeOut);
                for(UInt32 ch=0;ch<2;++ch) {
                    const float s=input.samples[std::min(ch,t.channels-1)][i];
                    require(std::isfinite(s),"nonfinite source PCM");
                    const float val=s>0?s*t.positiveScale:s;
                    out.samples[ch][begin-at+i]+=val*fade*(ch?t.gainR:t.gainL);
                }
            }
        }
        std::erase_if(voices,[&](const auto& v){return v->clip->at+v->clip->count<=at+n;});
    }
    void verify() const {for(const auto& t:tracks)t.verify();}
};
}
