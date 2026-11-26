#import <Foundation/Foundation.h>
#import <AudioToolbox/AudioToolbox.h>
#include <dlfcn.h>
#include "include/MasterDSP.hpp"
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/stat.h>

namespace {
constexpr UInt32 blockSize = 1024;
void require(bool ok, const char* why) {
    if (!ok) throw std::runtime_error(why);
}
void checked(OSStatus status, const char* action) {
    if (status != noErr)
        throw std::runtime_error(std::string(action) + " (OSStatus " + std::to_string(status) + ")");
}
NSURL* urlFor(const char* path) {
    NSString* p = [[NSFileManager defaultManager] stringWithFileSystemRepresentation:path length:strlen(path)];
    return [NSURL fileURLWithPath:p].absoluteURL.URLByStandardizingPath;
}
struct AudioFile {
    ExtAudioFileRef ref = nullptr;
    void finish() {
        if (!ref) return;
        ExtAudioFileRef owned = ref;
        ref = nullptr;
        checked(ExtAudioFileDispose(owned), "close audio file");
    }
    ~AudioFile() { if (ref) ExtAudioFileDispose(ref); }
    template<class T> T get(ExtAudioFilePropertyID id) const {
        T value{};
        UInt32 size = sizeof(value);
        checked(ExtAudioFileGetProperty(ref,id,&size,&value), "read file property");
        return value;
    }
    void clientFormat(const AudioStreamBasicDescription& format) {
        checked(ExtAudioFileSetProperty(ref,kExtAudioFileProperty_ClientDataFormat,sizeof(format),&format),
                "set client PCM format");
    }
};
AudioStreamBasicDescription format(double rate, UInt32 channels, bool planar) {
    AudioStreamBasicDescription f{};
    f.mSampleRate=rate;
    f.mFormatID=kAudioFormatLinearPCM;
    f.mFormatFlags=kAudioFormatFlagsNativeFloatPacked;
    if (planar) f.mFormatFlags |= kAudioFormatFlagIsNonInterleaved;
    f.mChannelsPerFrame=channels;
    f.mBitsPerChannel=32;
    f.mFramesPerPacket=1;
    f.mBytesPerPacket=f.mBytesPerFrame=sizeof(float)*(planar ? 1 : channels);
    return f;
}
struct List {
    UInt32 count{};
    AudioBuffer channels[2]{};
    AudioBufferList* ptr() { return reinterpret_cast<AudioBufferList*>(this); }
};
static_assert(offsetof(List,channels)==offsetof(AudioBufferList,mBuffers));
struct Block {
    std::array<std::array<float,blockSize>,2> samples{};
    List buffers(UInt32 channels, UInt32 n, UInt32 offset=0) {
        List list;
        list.count=channels;
        for (UInt32 c=0;c<channels;++c)
            list.channels[c]={1,static_cast<UInt32>(n*sizeof(float)),samples[c].data()+offset};
        return list;
    }
};
struct Source {
    Block block;
    SInt64 cursor=0;
    UInt32 length=0, channels=0;
};
OSStatus supply(void* ref,AudioUnitRenderActionFlags*,const AudioTimeStamp* ts,UInt32,
                UInt32 frames,AudioBufferList* buffers) {
    const auto& s=*static_cast<const Source*>(ref);
    if (buffers->mNumberBuffers!=s.channels || frames!=s.length || ts->mSampleTime!=s.cursor)
        return kAudioUnitErr_InvalidPropertyValue;
    for (UInt32 c=0;c<s.channels;++c) {
        auto& b=buffers->mBuffers[c];
        if (!b.mData || b.mDataByteSize<frames*sizeof(float)) return kAudio_ParamError;
        memcpy(b.mData,s.block.samples[c].data(),frames*sizeof(float));
        b.mDataByteSize=frames*sizeof(float);
    }
    return noErr;
}
struct Unit {
    AudioUnit ref=nullptr;
    ~Unit() { if(ref) AudioComponentInstanceDispose(ref); }
    template<class T> void set(AudioUnitPropertyID id,const T& value,AudioUnitScope scope=kAudioUnitScope_Global) {
        checked(AudioUnitSetProperty(ref,id,scope,0,&value,sizeof(value)),"set AU property");
    }
    template<class T> T get(AudioUnitPropertyID id) {
        T value{};
        UInt32 size=sizeof(value);
        checked(AudioUnitGetProperty(ref,id,kAudioUnitScope_Global,0,&value,&size),"get AU property");
        require(size==sizeof(value),"AU property size mismatch");
        return value;
    }
    void load(NSURL* url, bool printPath=true) {
        NSBundle* bundle=[NSBundle bundleWithURL:url];
        require(bundle && bundle.executableURL,"component bundle not found");
        // The symbol is obtained from the supplied executable, never from the global AU registry.
        void* module=dlopen(bundle.executableURL.fileSystemRepresentation,RTLD_NOW|RTLD_LOCAL);
        if (!module) throw std::runtime_error(dlerror());
        auto factory=reinterpret_cast<AudioComponentFactoryFunction>(dlsym(module,"OutputMasterFactory"));
        require(factory,"OutputMasterFactory symbol missing");
        AudioComponentDescription desc{'aufx','ObMs','OtAu',kAudioComponentFlag_SandboxSafe,0};
        AudioComponent component=AudioComponentRegister(&desc, CFSTR("Output Audio: Output Master test instance"), 0, factory);
        require(component,"process-local AU registration failed");
        checked(AudioComponentInstanceNew(component,&ref),"instantiate component");
        if (printPath) std::printf("component=%s version=%s\n", bundle.executableURL.fileSystemRepresentation,
                    [[bundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] UTF8String]);
    }
    void pass(AudioFile& input,AudioFile* output,SInt64 frames,UInt32 delay,Source& source) {
        checked(ExtAudioFileSeek(input.ref,0),"rewind input");
        checked(AudioUnitReset(ref,kAudioUnitScope_Global,0),"reset render state");
        const SInt64 end=frames+delay;
        Block wet;
        SInt64 written=0;
        for(SInt64 at=0;at<end;) {
            const UInt32 n=static_cast<UInt32>(std::min<SInt64>(blockSize,end-at));
            const UInt32 fromFile=static_cast<UInt32>(std::clamp<SInt64>(frames-at,0,n));
            if(fromFile) {
                auto data=source.block.buffers(source.channels,fromFile);
                UInt32 read=fromFile;
                checked(ExtAudioFileRead(input.ref,&read,data.ptr()),"read input");
                require(read==fromFile,"truncated input");
            }
            for(UInt32 c=0;c<source.channels;++c)
                std::fill_n(source.block.samples[c].data()+fromFile,n-fromFile,0.f);
            source.cursor=at;
            source.length=n;
            AudioTimeStamp stamp{};
            stamp.mFlags=kAudioTimeStampSampleTimeValid;
            stamp.mSampleTime=double(at);
            AudioUnitRenderActionFlags flags=0;
            auto rendered=wet.buffers(source.channels,n);
            checked(AudioUnitRender(ref,&flags,&stamp,0,n,rendered.ptr()),"render AU");
            const UInt32 skip=static_cast<UInt32>(std::clamp<SInt64>(SInt64(delay)-at,0,n));
            if(output && skip<n) {
                const UInt32 keep=n-skip;
                for(UInt32 c=0;c<source.channels;++c)
                    for(UInt32 i=skip;i<n;++i)
                        require(std::isfinite(wet.samples[c][i]),"nonfinite processed sample");
                auto slice=wet.buffers(source.channels,keep,skip);
                checked(ExtAudioFileWrite(output->ref,keep,slice.ptr()),"write processed frames");
                written+=keep;
            }
            at+=n;
        }
        require(!output || written==frames,"output frame count differs from input");
    }
};
// The display ABI may evolve independently of the render command protocol.
void logDisplay(Unit& unit,const char* label) {
    UInt32 size=0;
    Boolean writable=false;
    checked(AudioUnitGetPropertyInfo(unit.ref,om::displayProperty,kAudioUnitScope_Global,0,&size,&writable),
            "check display ABI");
    if(size!=sizeof(om::Display)) return;
    const auto d=unit.get<om::Display>(om::displayProperty);
    std::printf("%s status=%u captured_s=%.3f input_lufs=%.3f output_lufs=%.3f peak_dbtp=%.3f",
                label,d.status,d.seconds,d.inputLU,d.outputLU,d.truePeak);
    if (d.status==om::mastered) {
        std::printf(" profile=");
        for (auto value:d.active) std::printf(" %.3f",value);
    }
    std::puts("");
}
struct PartialFile {
    NSURL* url=nil;
    ~PartialFile() { if (url) [[NSFileManager defaultManager] removeItemAtURL:url error:nil]; }
};
void checkNewDestination(NSURL* url) {
    require(![[NSFileManager defaultManager] fileExistsAtPath:url.path],"output already exists");
}
NSURL* neighborTemporary(NSURL* destination,NSString* suffix) {
    return [destination.URLByDeletingLastPathComponent
        URLByAppendingPathComponent:[[NSUUID UUID].UUIDString stringByAppendingString:suffix]];
}
void stagePreset(Unit& unit,NSURL* temp,NSURL* finalPath) {
    CFPropertyListRef state=unit.get<CFPropertyListRef>(kAudioUnitProperty_ClassInfo);
    require(state,"AU did not supply ClassInfo");
    id object=CFBridgingRelease(state);
    require([object isKindOfClass:[NSDictionary class]],"unexpected AU ClassInfo type");
    NSMutableDictionary* preset=[object mutableCopy];
    preset[@"name"]=finalPath.lastPathComponent.stringByDeletingPathExtension;
    NSError* error=nil;
    NSData* xml=[NSPropertyListSerialization dataWithPropertyList:preset format:NSPropertyListXMLFormat_v1_0
        options:0 error:&error];
    if (!xml || ![xml writeToURL:temp options:NSDataWritingWithoutOverwriting error:&error])
        throw std::runtime_error(error.localizedDescription.UTF8String);
}
// A staged file and its destination always share a directory. renamex_np never replaces an existing file.
void publishFile(NSURL* staged,NSURL* finalPath) {
    if (renamex_np(staged.fileSystemRepresentation,finalPath.fileSystemRepresentation,RENAME_EXCL)!=0)
        throw std::runtime_error(std::string("publish ")+finalPath.fileSystemRepresentation+": "+strerror(errno));
}
struct Setting { unsigned id; float value; };
void listParameters(NSURL* url) {
    Unit unit;
    unit.load(url,false);
    UInt32 bytes=0;
    Boolean writable=false;
    checked(AudioUnitGetPropertyInfo(unit.ref,kAudioUnitProperty_ParameterList,kAudioUnitScope_Global,
                                     0,&bytes,&writable),"read AU parameter list size");
    require(bytes%sizeof(AudioUnitParameterID)==0,"invalid parameter list");
    std::vector<AudioUnitParameterID> ids(bytes/sizeof(AudioUnitParameterID));
    if (bytes) checked(AudioUnitGetProperty(unit.ref,kAudioUnitProperty_ParameterList,kAudioUnitScope_Global,
                                           0,ids.data(),&bytes),"read AU parameter IDs");
    std::sort(ids.begin(),ids.end());
    NSMutableArray* list=[NSMutableArray arrayWithCapacity:ids.size()];
    for (auto id:ids) {
        AudioUnitParameterInfo info{};
        UInt32 size=sizeof(info);
        checked(AudioUnitGetProperty(unit.ref,kAudioUnitProperty_ParameterInfo,kAudioUnitScope_Global,id,&info,&size),
                "read AU parameter info");
        NSString* name=[NSString stringWithUTF8String:info.name];
        if ((info.flags & kAudioUnitParameterFlag_HasCFNameString) && info.cfNameString)
            name=[(__bridge NSString*)info.cfNameString copy];
        if ((info.flags & kAudioUnitParameterFlag_CFNameRelease) && info.cfNameString)
            CFRelease(info.cfNameString);
        CFArrayRef labels=nullptr;
        size=sizeof(labels);
        const OSStatus labelStatus=AudioUnitGetProperty(unit.ref,kAudioUnitProperty_ParameterValueStrings,
                                                       kAudioUnitScope_Global,id,&labels,&size);
        NSArray* values=(labelStatus==noErr && labels) ? CFBridgingRelease(labels) : @[];
        [list addObject:@{@"id":@(id),@"name":name ?: @"",@"min":@(info.minValue),@"max":@(info.maxValue),
                          @"default":@(info.defaultValue),@"unit":@(info.unit),@"values":values}];
    }
    NSError* error=nil;
    NSData* data=[NSJSONSerialization dataWithJSONObject:list options:NSJSONWritingSortedKeys error:&error];
    if (!data) throw std::runtime_error(error.localizedDescription.UTF8String);
    require(std::fwrite(data.bytes,1,data.length,stdout)==data.length,"write AU parameter manifest");
    std::puts("");
}
void run(int argc,const char* argv[]) {
    if (argc==3 && std::string(argv[1])=="--parameters") { listParameters(urlFor(argv[2])); return; }
    require(argc>=4,"usage: render COMPONENT INPUT OUTPUT [--save-preset NEW.aupreset] [--bypass] [--set PARAMETER_ID VALUE] ...");
    const auto componentURL=urlFor(argv[1]), inputURL=urlFor(argv[2]), outputURL=urlFor(argv[3]);
    bool bypass=false;
    NSURL* presetURL=nil;
    std::vector<Setting> settings;
    for(int i=4;i<argc;++i) {
        const std::string arg=argv[i];
        if(arg=="--save-preset") {
            require(!presetURL && i+1<argc,"expected --save-preset NEW.aupreset once");
            presetURL=urlFor(argv[++i]);
            require([presetURL.pathExtension caseInsensitiveCompare:@"aupreset"]==NSOrderedSame,"expected .aupreset extension");
            checkNewDestination(presetURL);
            continue;
        }
        if(arg=="--bypass") { bypass=true; continue; }
        require(arg=="--set" && i+2<argc,"expected --set PARAMETER_ID VALUE");
        char* idEnd=nullptr;
        const auto id=strtoul(argv[++i],&idEnd,10);
        require(*argv[i] && !*idEnd && id<=UINT32_MAX,"invalid parameter ID");
        char* valueEnd=nullptr;
        const auto value=strtof(argv[++i],&valueEnd);
        require(*argv[i] && !*valueEnd && std::isfinite(value),"invalid parameter value");
        settings.push_back({static_cast<unsigned>(id),value});
    }
    require(!presetURL || ![presetURL isEqual:outputURL],"WAV and preset must use distinct paths");
    checkNewDestination(outputURL);
    AudioFile input;
    checked(ExtAudioFileOpenURL((__bridge CFURLRef)inputURL,&input.ref),"open input");
    auto fileFormat=input.get<AudioStreamBasicDescription>(kExtAudioFileProperty_FileDataFormat);
    const auto frames=input.get<SInt64>(kExtAudioFileProperty_FileLengthFrames);
    require(frames>0 && (fileFormat.mChannelsPerFrame==1 || fileFormat.mChannelsPerFrame==2),"expected mono/stereo audio");
    auto planar=format(fileFormat.mSampleRate,fileFormat.mChannelsPerFrame,true);
    input.clientFormat(planar);

    Unit unit;
    unit.load(componentURL);
    Source source;
    source.channels=planar.mChannelsPerFrame;
    unit.set(kAudioUnitProperty_StreamFormat,planar,kAudioUnitScope_Input);
    unit.set(kAudioUnitProperty_StreamFormat,planar,kAudioUnitScope_Output);
    unit.set(kAudioUnitProperty_MaximumFramesPerSlice,blockSize);
    unit.set(kAudioUnitProperty_SetRenderCallback,AURenderCallbackStruct{supply,&source},kAudioUnitScope_Input);
    checked(AudioUnitInitialize(unit.ref),"initialize");
    for(const auto& setting:settings) {
        checked(AudioUnitSetParameter(unit.ref,setting.id,kAudioUnitScope_Global,0,setting.value,0),"set AU parameter");
        float actual=0;
        checked(AudioUnitGetParameter(unit.ref,setting.id,kAudioUnitScope_Global,0,&actual),"read parameter");
        require(std::abs(actual-setting.value)<1e-5,"parameter did not take requested value");
    }

    unit.set(om::commandProperty,UInt32(om::learn));
    unit.pass(input,nullptr,frames,0,source);
    logDisplay(unit,"learned");
    unit.set(om::commandProperty,UInt32(om::apply));
    PartialFile stagedPreset;
    if (presetURL) {
        stagedPreset.url=neighborTemporary(presetURL,@".partial.aupreset");
        stagePreset(unit,stagedPreset.url,presetURL);
    }
    unit.set(kAudioUnitProperty_OfflineRender,UInt32(1));
    if(bypass) unit.set(kAudioUnitProperty_BypassEffect,UInt32(1));
    const auto delaySeconds=unit.get<double>(kAudioUnitProperty_Latency);
    require(std::isfinite(delaySeconds) && delaySeconds>=0 && delaySeconds<10,"invalid reported AU latency");
    const auto delay=static_cast<UInt32>(std::llround(delaySeconds*planar.mSampleRate));
    PartialFile temp{neighborTemporary(outputURL,@".partial.wav")};
    AudioFile output;
    auto packed=format(planar.mSampleRate,source.channels,false);
    checked(ExtAudioFileCreateWithURL((__bridge CFURLRef)temp.url,kAudioFileWAVEType,&packed,nullptr,0,&output.ref),
            "create float WAV");
    output.clientFormat(planar);
    unit.pass(input,&output,frames,delay,source);
    output.finish();
    logDisplay(unit,"exported");
    struct stat presetIdentity{};
    if (presetURL) {
        require(lstat(stagedPreset.url.fileSystemRepresentation,&presetIdentity)==0,"stat staged preset");
        publishFile(stagedPreset.url,presetURL);
        stagedPreset.url=nil;
    }
    try {
        publishFile(temp.url,outputURL);
        temp.url=nil;
    } catch (...) {
        struct stat current{};
        if (presetURL && lstat(presetURL.fileSystemRepresentation,&current)==0 &&
            current.st_dev==presetIdentity.st_dev && current.st_ino==presetIdentity.st_ino)
            [[NSFileManager defaultManager] removeItemAtURL:presetURL error:nil];
        throw;
    }
    std::printf("rate=%.0f channels=%u frames=%lld latency_compensated=%u bypass=%u file=%s\n",
                planar.mSampleRate,source.channels,static_cast<long long>(frames),delay,bypass,outputURL.fileSystemRepresentation);
}
}
int main(int argc,const char* argv[]) {
    @autoreleasepool {
        try { run(argc,argv); return 0; }
        catch(const std::exception& error) { std::fprintf(stderr,"render: %s\n",error.what()); return 1; }
    }
}
