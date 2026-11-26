// Preserve the accepted single-file host and its --parameters interface.
#define main legacyMain
#include "renderer.inc"
#undef main
#include "arrangement.inc"
#include <iostream>

namespace bus {
class BusAU {
    Unit unit;
    Source source;
    Frame cursor=0;
    bool primed=false;
    Block wet;
    void raw(UInt32 n) {
        const UInt32 content=UInt32(std::clamp<Frame>(mix.length-cursor,0,n));
        if (content) mix.mix(cursor,content,source.block);
        for (auto& ch:source.block.samples) std::fill_n(ch.data()+content,n-content,0.f);
        source.cursor=cursor;
        source.length=n;
        AudioTimeStamp stamp{};
        stamp.mFlags=kAudioTimeStampSampleTimeValid;
        stamp.mSampleTime=double(cursor);
        AudioUnitRenderActionFlags flags=0;
        auto result=wet.buffers(2,n);
        checked(AudioUnitRender(unit.ref,&flags,&stamp,0,n,result.ptr()),"render native master bus");
        cursor+=n;
    }
    void reset(Frame at) {
        mix.reset();
        cursor=at;
        checked(AudioUnitReset(unit.ref,kAudioUnitScope_Global,0),"reset native master bus");
    }
public:
    Arrangement& mix;
    UInt32 delay=0;
    Frame position=0;
    BusAU(Arrangement& input,NSURL* component):mix(input) {
        unit.load(component,false);
        source.channels=2;
        auto io=format(mix.rate,2,true);
        unit.set(kAudioUnitProperty_StreamFormat,io,kAudioUnitScope_Input);
        unit.set(kAudioUnitProperty_StreamFormat,io,kAudioUnitScope_Output);
        unit.set(kAudioUnitProperty_MaximumFramesPerSlice,blockSize);
        unit.set(kAudioUnitProperty_SetRenderCallback,AURenderCallbackStruct{supply,&source},kAudioUnitScope_Input);
        checked(AudioUnitInitialize(unit.ref),"initialize bus AU");
        const auto d=unit.get<double>(kAudioUnitProperty_Latency);
        require(std::isfinite(d) && d>=0 && d<10,"invalid AU latency");
        delay=UInt32(std::llround(d*mix.rate));
    }
    void setValue(const Setting& setting) {
        AudioUnitParameterInfo info{};
        UInt32 size=sizeof(info);
        checked(AudioUnitGetProperty(unit.ref,kAudioUnitProperty_ParameterInfo,kAudioUnitScope_Global,
                                     setting.id,&info,&size),"read bus AU parameter range");
        if ((info.flags & kAudioUnitParameterFlag_CFNameRelease) && info.cfNameString) CFRelease(info.cfNameString);
        const bool discrete=info.unit==kAudioUnitParameterUnit_Indexed || info.unit==kAudioUnitParameterUnit_Boolean;
        require((info.flags & kAudioUnitParameterFlag_IsWritable) && std::isfinite(setting.value)
                && setting.value>=info.minValue && setting.value<=info.maxValue
                && (!discrete || std::floor(setting.value)==setting.value),"AU parameter outside its declared range");
        checked(AudioUnitSetParameter(unit.ref,setting.id,kAudioUnitScope_Global,0,setting.value,0),"set bus AU parameter");
        float actual=0;
        checked(AudioUnitGetParameter(unit.ref,setting.id,kAudioUnitScope_Global,0,&actual),"read back bus AU parameter");
        require(std::abs(actual-setting.value)<1e-5,"AU parameter out of range");
    }
    bool applied() {return unit.get<om::Display>(om::displayProperty).status==om::mastered;}
    void restore(NSURL* preset) {
        NSNumber* size=nil;
        require([preset getResourceValue:&size forKey:NSURLFileSizeKey error:nil] && size.unsignedLongLongValue<=1024*1024,
                "preset unavailable or too large");
        NSData* data=[NSData dataWithContentsOfURL:preset];
        require(data,"cannot read preset");
        id value=[NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable format:nil error:nil];
        require([value isKindOfClass:NSDictionary.class],"invalid preset");
        CFPropertyListRef property=(__bridge CFPropertyListRef)value;
        unit.set(kAudioUnitProperty_ClassInfo,property);
        require(applied(),"preset has no applied mastering profile");
    }
    void learn() {
        setBypass(false);
        unit.set(kAudioUnitProperty_OfflineRender,UInt32(0));
        unit.set(om::commandProperty,UInt32(om::learn));
        reset(0);
        while(cursor<mix.length) raw(UInt32(std::min<Frame>(blockSize,mix.length-cursor)));
        mix.verify();
        unit.set(om::commandProperty,UInt32(om::apply));
        require(applied(),"AU did not apply the profile");
    }
    void save(NSURL* temp,NSURL* final) {stagePreset(unit,temp,final);}
    void offline(bool value) {unit.set(kAudioUnitProperty_OfflineRender,UInt32(value));}
    void setBypass(bool on) {unit.set(kAudioUnitProperty_BypassEffect,UInt32(on));}
    void seek(Frame to,bool exact=false) {
        require(to>=0 && to<=mix.length,"seek outside arrangement");
        // Fast transport seeks restart with a three-second local pre-roll. Exact seeks
        // replay the prefix for a sample-matched reference to a continuous bounce.
        const Frame start=exact?0:(std::max<Frame>(0,to-3*mix.rate) / 32) * 32;
        reset(start);
        const Frame target=to+delay;
        while(cursor<target) raw(UInt32(std::min<Frame>(blockSize,target-cursor)));
        position=to;
        primed=true;
    }
    template<class Sink> void pull(Frame count,Sink&& sink) {
        if (!primed) seek(0);
        require(count>=0 && count<=mix.length-position,"read outside arrangement");
        while(count>0) {
            const UInt32 n=UInt32(std::min<Frame>(blockSize,count));
            raw(n);
            for (const auto& ch:wet.samples)
                for(UInt32 i=0;i<n;++i) require(std::isfinite(ch[i]),"nonfinite master signal");
            sink(wet,n);
            position+=n;
            count-=n;
        }
    }
};
void reply(NSDictionary* data) {
    NSData* bytes=[NSJSONSerialization dataWithJSONObject:data options:0 error:nil];
    require(bytes && fwrite(bytes.bytes,1,bytes.length,stdout)==bytes.length && putchar('\n')!=EOF,"write monitor metadata");
    fflush(stdout);
}
void monitor(BusAU& engine) {
    reply(@{@"ready":@YES,@"sampleRate":@(engine.mix.rate),@"frames":@(engine.mix.length),
            @"latencyFrames":@(engine.delay),@"channels":@2,@"encoding":@"f32le",@"applied":@(engine.applied())});
    std::string line;
    while(std::getline(std::cin,line)) { @autoreleasepool {
        require(line.size()<=8192,"monitor request too large");
        NSData* bytes=[NSData dataWithBytes:line.data() length:line.size()];
        id cmd=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
        require([cmd isKindOfClass:NSDictionary.class],"invalid monitor request");
        const auto op=textField(cmd,@"op");
        if(op=="quit") {reply(@{@"closed":@YES});return;}
        if(op=="seek") {
            engine.seek(integer(cmd[@"frame"],0,engine.mix.length,"invalid seek frame"),flag(cmd,@"exact"));
            reply(@{@"nextFrame":@(engine.position)});continue;
        }
        if(op=="set") {
            const auto id=integer(cmd[@"id"],0,UINT32_MAX,"invalid AU parameter ID");
            require(number(cmd[@"value"]) && std::isfinite([cmd[@"value"] doubleValue]),"expected a finite AU parameter");
            const float value=[cmd[@"value"] floatValue];
            engine.setValue({unsigned(id),value});
            reply(@{@"id":@(id),@"value":@(value),@"nextFrame":@(engine.position)});continue;
        }
        if(op=="bypass") {
            require(cmd[@"enabled"],"expected enabled");bool on=flag(cmd,@"enabled");
            if(!on && !engine.applied()) {
                reply(@{@"error":@"applied profile required",@"nextFrame":@(engine.position)});continue;
            }
            engine.setBypass(on);reply(@{@"bypass":@(on),@"nextFrame":@(engine.position)});continue;
        }
        require(op=="read","unknown monitor op");
        const Frame requested=integer(cmd[@"frames"],1,262144,"invalid monitor read size");
        if(cmd[@"bypass"]) {
            const bool on=flag(cmd,@"bypass");
            if(!on && !engine.applied()) {
                reply(@{@"error":@"applied profile required",@"nextFrame":@(engine.position)});continue;
            }
            engine.setBypass(on);
        }
        const Frame available=std::min(requested,engine.mix.length-engine.position);
        const auto start=engine.position;
        std::vector<float> pcm;
        pcm.reserve(2*available);
        engine.mix.verify();
        engine.pull(available,[&](Block& wet,UInt32 n) {
            for(UInt32 i=0;i<n;++i) {
                pcm.push_back(wet.samples[0][i]);pcm.push_back(wet.samples[1][i]);
            }
        });
        engine.mix.verify();
        reply(@{@"start":@(start),@"frames":@(available),@"eof":@(start+available==engine.mix.length)});
        require(pcm.empty() || fwrite(pcm.data(),sizeof(float),pcm.size(),stdout)==pcm.size(),"write monitor PCM");
        fflush(stdout);
    }}
}
void runBus(int argc,const char* argv[]) {
    const std::string mode(argv[1]);
    const bool live=mode=="--monitor", analyze=mode=="--analyze";
    require(argc>=(live?4:5),"expected --bus/--analyze COMPONENT MANIFEST NEW_OUTPUT or --monitor COMPONENT MANIFEST");
    NSURL* component=urlFor(argv[2]);NSURL* manifest=urlFor(argv[3]);
    NSURL* destination=live?nil:urlFor(argv[4]);
    if(destination)checkNewDestination(destination);
    NSURL* saveURL=nil;NSURL* loadURL=nil;
    std::vector<Setting> settings;
    bool bypass=false;
    for(int i=live?4:5;i<argc;++i) {
        const std::string option(argv[i]);
        if(option=="--bypass") {bypass=true;continue;}
        if(option=="--save-preset" || option=="--load-preset") {
            require(i+1<argc,"missing preset path");
            NSURL* url=urlFor(argv[++i]);
            if(option=="--save-preset") {
                require(!live && !analyze && !saveURL && ![url isEqual:destination],"invalid preset destination");
                checkNewDestination(url);saveURL=url;
            } else {require(!loadURL,"duplicate input preset");loadURL=url;}
            continue;
        }
        require(option=="--set" && i+2<argc,"unknown bus option");
        char* end=nullptr;
        const auto id=std::strtoul(argv[++i],&end,10);require(*argv[i] && !*end && id<=UINT32_MAX,"invalid parameter ID");
        const float value=std::strtof(argv[++i],&end);require(*argv[i] && !*end && std::isfinite(value),"invalid parameter value");
        settings.push_back({unsigned(id),value});
    }
    require(!analyze || (!loadURL && !bypass),"analysis requires a new applied profile");
    Arrangement arrangement(readJSON(manifest));BusAU engine(arrangement,component);
    if(loadURL)engine.restore(loadURL);
    for(const auto& s:settings)engine.setValue(s);
    // A bypass-only export is valid even when the arrangement is silent.
    if(!loadURL && (!bypass || saveURL))engine.learn();
    if(analyze) {
        PartialFile preset{neighborTemporary(destination, @".partial.aupreset")};
        engine.save(preset.url,destination);
        arrangement.verify();
        publishFile(preset.url,destination);preset.url=nil;
        reply(@{@"applied":@YES,@"rate":@(arrangement.rate),@"frames":@(arrangement.length),@"tracks":@(arrangement.tracks.size())});
        return;
    }
    engine.offline(!live);engine.setBypass(bypass);
    if(live){monitor(engine);return;}
    PartialFile staged{neighborTemporary(destination,@".partial.wav")};
    PartialFile preset;
    if(saveURL){preset.url=neighborTemporary(saveURL,@".partial.aupreset");engine.save(preset.url,saveURL);}
    AudioFile output;
    const auto packed=format(arrangement.rate,2,false);
    checked(ExtAudioFileCreateWithURL((__bridge CFURLRef)staged.url,kAudioFileWAVEType,&packed,nullptr,0,&output.ref),"create master output");
    output.clientFormat(format(arrangement.rate,2,true));
    engine.pull(arrangement.length,[&](Block& wet,UInt32 n){
        auto data=wet.buffers(2,n);checked(ExtAudioFileWrite(output.ref,n,data.ptr()),"write master frames");
    });
    arrangement.verify();output.finish();
    struct stat identity{};
    if(saveURL){
        require(lstat(preset.url.fileSystemRepresentation,&identity)==0,"stat preset");
        publishFile(preset.url,saveURL);preset.url=nil;
    }
    try {publishFile(staged.url,destination);staged.url=nil;}
    catch (...) {
        struct stat observed{};
        if(saveURL && lstat(saveURL.fileSystemRepresentation,&observed)==0 &&
            identity.st_dev==observed.st_dev && identity.st_ino==observed.st_ino)
            [[NSFileManager defaultManager] removeItemAtURL:saveURL error:nil];
        throw;
    }
    reply(@{@"rate":@(arrangement.rate),@"frames":@(arrangement.length),@"tracks":@(arrangement.tracks.size()),@"latencyFrames":@(engine.delay),@"bypass":@(bypass)});
}
}
int main(int argc,const char* argv[]) {
    if(argc<2 || (std::string(argv[1])!="--bus" && std::string(argv[1])!="--monitor" && std::string(argv[1])!="--analyze"))return legacyMain(argc,argv);
    @autoreleasepool {
        try {bus::runBus(argc,argv);return 0;}
        catch(const std::exception& e){fprintf(stderr,"bus: %s\n",e.what());return 1;}
    }
}
