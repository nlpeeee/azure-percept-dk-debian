# Applications for the Azure Percept DK after Azure

Research date: 23 October 2026. Focus: the user's Debian ARM64 carrier board, Vision module and newly acquired Audio module, with particular interest in interactive music and children's projects.

## Findings and recommendation

The best first project is a **camera-controlled musical tabletop**: move physical cards or blocks to arrange loops, choose instruments and change effects. The same input system can support storytelling, simple games and physical programming. It offers several applications from one modest software foundation.

For a useful appliance, choose a **workbench recorder with a “save the last minute” control**. For a project using all three boards, choose a **sound sampler controlled by physical cards**, once audio capture works. For an existing application to adapt, investigate **Linux Voice Assistant as a Home Assistant satellite**.

These recommendations are engineering judgments based on the repository's tests and the primary sources below. None of the proposed applications was installed, benchmarked or run on the board during this research. No SSH, firmware update, build or board operation was performed.

### What the hardware actually gives us

| Component | Evidence available | Consequence for applications |
|---|---|---|
| Debian ARM64 carrier | Repository records four Cortex-A53 cores and working access to approximately 4 GiB RAM. Later CPU notes supersede earlier fixed-frequency notes. | Suitable candidate for image processing, event logic, small audio tasks and serving a local interface. Do not assume Raspberry Pi 4 performance. |
| Vision camera | Real offline 720p recording demonstrated. H.264 streaming sustained delivery around real time in the documented test. | Recording and frame analysis have an established starting point. |
| Camera access | Sensor is behind Myriad X and the proprietary Microsoft runtime; no ordinary UVC webcam interface. | Use the existing isolated runtime and RTSP output. Generic webcam applications need an adapter. |
| Vision inference | Bundled inference loop runs; useful detection accuracy and custom models remain unvalidated. | Do not base a quick project on the assumption that person, hand or object recognition already works. |
| Myriad X | Vendor toolchain is based on OpenVINO 2021.1 with supported-operation restrictions. | Custom accelerated models are a separate development effort, not a universal accelerator for current packages. |
| Carrier GPU/video decoder | Offscreen GPU rendering and Hantro video decoding have passed repository tests. | Useful infrastructure, but neither proves browser acceleration, physical display output or arbitrary ML acceleration. |
| Audio module | Four-microphone array is documented by ASUS; local project notes last tested the board without it attached. | Audio-dependent ideas have a common capture/playback qualification gate. Raw microphone channels, direction finding and echo cancellation are not established. |
| Outputs and connections | Ethernet and USB host work; Bluetooth scanning was tested. Display output and Linux USB gadget operation are unproven. | A laptop/tablet browser is the lowest-risk first display. A speaker/output device must be selected and tested. |

Local evidence: [camera](<LOCAL_PATH>/docs/camera-vision.md), [GPU/video](<LOCAL_PATH>/docs/gpu-vpu-plan.md), [CPU](<LOCAL_PATH>/docs/cpu-power-status.md), [CPU measurements](<LOCAL_PATH>/docs/cpu-benchmarks.md), [USB-C](<LOCAL_PATH>/docs/usb-c.md). Audio specification: [ASUS](https://www.asus.com/networking-iot-servers/aiot-industrial-solutions/embedded-computers-edge-ai-systems/azure-percept-audio/).

The repository README contains historical claims contradicted by later test notes. This report uses the later evidence without proposing any kernel or bootloader changes. It assumes ordinary application development on the existing working installation.

## Ranking the opportunities

**High fit** means the first version can use simple algorithms or known recording paths. **Conditional** means an important device, integration or performance question remains. **Research** means it should not be presented as an easy implementation.

Effort estimates are my rough estimates for a developer's basic prototype after the relevant inputs and outputs work, not delivery promises. “Small” means roughly 1–3 focused days; “medium” means roughly 4–10; “research” has no reliable estimate. Child-friendly polish, physical construction and a reliable appliance take additional work.

| # | Application | Fit / effort | Ear needed? | Additional equipment or compute |
|---|---|---|---|---|
| 1 | Musical blocks / tabletop sequencer | High / small | Optional | Printed tags, overhead mount, browser with speaker |
| 2 | Sound-catching sampler | Conditional / small | Yes | Cards and speaker; browser can play samples |
| 3 | Conducting wand / continuous musical controller | High / small | Optional | Bright wand or tagged paddle; speaker |
| 4 | Humming monster / voice-controlled visual game | Conditional / small | Yes | Browser display and speaker |
| 5 | Story cards and sound-effect theatre | High / small | Optional | Printed cards; recorded narration |
| 6 | Physical coding cards | High / medium | Optional | Printed arrows; browser maze; robot optional |
| 7 | Stop-motion and Foley studio | High / small | Optional for first version | Camera stand, lighting, browser |
| 8 | Movement games and reactive art | High for coarse motion / medium | Optional | Browser on large screen; projector optional |
| 9 | Cooperative escape-room controller | High / medium | Optional | Cards/props; LEDs or microcontroller optional |
| 10 | Workbench rewind and experiment notebook | High / medium | Optional | External storage or NAS for extensive recording |
| 11 | Document camera and printed-text reader | Conditional / medium | No | Lighting, stand, speaker; optional PC OCR |
| 12 | Home Assistant voice satellite | Conditional / medium | Yes | Existing Home Assistant host and speaker |
| 13 | Wildlife audio/video diary | High for recording; conditional for AI / medium | Yes for sound | Sheltered mounting; PC recommended for classification |
| 14 | Machine sound and motion diary | Conditional / medium | Yes | Fixed position near one machine |
| 15 | LEGO/USB robot controller | Conditional / medium | Optional | Compatible robot/hub or MCU; motor power |
| 16 | Conference/document-camera accessory | Conditional / medium; standalone Teams research | Yes for conferencing | PC running meeting software and speaker |

For camera-only activities, the Ear does not need to be working before development starts. Browser sound comes from the browser's computer/tablet, not magically from the Percept board. The first browser version needs a user action to enable sound.

## Music, play and learning

### 1. Musical blocks: the strongest first choice

**Experience:** put a drum block on a paper grid, add bass and a melody, rotate a block to change its variation, and move blocks between columns to change the pattern. Children can make something musical without accurate timing or reading text.

**Precedent:** reacTIVision was developed as the visual tracking component of the Reactable tangible synthesizer. It tracks marked objects and emits control information; it does not include the Reactable sound engine. This is an established interaction, not a Percept-specific project. [reacTIVision](https://reactivision.sourceforge.net/)

**Proposed implementation:** keep the camera fixed above the table. Use large ArUco tags on the top of blocks, read identity/position/orientation, and send changes to a browser sequencer. OpenCV supplies marker detection, while Tone.js supplies audio scheduling. [ArUco documentation](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html) · [Tone.js](https://tonejs.github.io/)

**First prototype:** four tagged cards, four loops, a printed four-zone mat, and changes applied at the next bar. Render icons and transport position in the browser; a video preview is optional. Use brief stability filtering so a hand covering a tag does not cause musical flickering.

**Main limitation:** camera latency and occlusion. They are manageable when the camera chooses arrangements and a separate audio clock keeps time. Accurate drumming is a different requirement. Mount tags facing the camera; a Reactable-style underside camera would need a different physical surface.

### 2. Sound-catching sampler

**Experience:** record a “boing,” a funny voice or a tap, assign it to a creature card, then play it backwards, faster or in a repeating rhythm by moving the card.

**Proposed implementation:** short microphone recordings stored as WAV, the same card detector as project 1, and a sample player in the browser. Begin with separate record and playback phases, which avoids feedback and does not require working echo cancellation. For a standalone sound engine, Pure Data is an established Linux music system and Debian trixie provides an ARM64 package. [Pure Data](https://github.com/pure-data/pure-data) · [Debian package](https://packages.debian.org/trixie/puredata-core)

**First prototype:** four two-second recordings, one card per sound, normal/reverse playback, and a simple loop mode. A browser button controls recording initially; voice commands are unnecessary.

**Main limitation:** the Ear must first yield usable audio. A browser microphone can help develop the interaction, but it would be a substitute input rather than evidence that the Ear works.

### 3. Conducting wand or continuous synthesizer

**Experience:** move a bright paddle up to raise pitch, sideways to change an effect, or into a zone to add an instrument. A marked cardboard dial can control a filter by rotation.

**Proposed implementation:** one coloured blob or printed tag, smoothing, and a constrained musical scale. Send control values to the same browser audio engine. A conventional local instrument can instead be driven through FluidSynth, which turns MIDI events into sound using a SoundFont. [FluidSynth introduction](https://github.com/FluidSynth/fluidsynth/blob/master/doc/wiki/GettingStarted.md)

**First prototype:** one sustained synthesizer voice with position controlling pitch and brightness. Keep volume limited in software and provide a clear stop control.

**Main limitation:** this should be described as an expressive camera instrument, not a precision theremin. Smooth continuous sound tolerates more delay than sharp note attacks.

### 4. Humming monster and sound experiments

**Experience:** hum to lift a creature, make a long sound to inflate it, or copy a short rhythm. Show a character card to choose its voice and appearance.

**Proposed implementation:** sound level for the first version; pitch estimates and onset detection later. Aubio provides these audio-analysis functions, and trixie packages Python bindings for ARM64. [Aubio](https://aubio.org/doc/latest/) · [Debian package](https://packages.debian.org/trixie/python3-aubio)

**First prototype:** animate mouth size from loudness and vertical position from a confidently detected sung pitch. Ignore pitch when the input is noisy or unvoiced. Add a “sound microscope” showing waveforms and a spectrogram to explain why humming and clapping look different.

**Main limitation:** microphone processing may alter signals, and pitch tracking becomes unreliable with several simultaneous voices. It is a playful one-person interaction, not a singing assessment tool.

### 5. Story cards and sound-effect theatre

**Experience:** arrange a dragon, forest and storm card to build a scene; reveal a character to hear its line; record alternative endings in family members' voices.

**Proposed implementation:** marker IDs select authored scenes, prerecorded dialogue and sound effects. Card combinations select branches in a finite story. No generative model is needed. Optional local text-to-speech could use Piper, subject to a small-model benchmark. [Piper upstream](https://github.com/OHF-Voice/piper1-gpl)

**First prototype:** six cards, three scene backgrounds and ten recorded lines, with a simple adult-facing interface for associating a recording with a card.

**Main limitation:** content creation takes more effort than recognition. Use artwork with a visible small tag rather than trying to recognise arbitrary toys. This is one of the easiest ways to get a polished result.

### 6. Physical coding cards

**Experience:** arrange forward, turn and repeat cards to guide an on-screen animal through a maze. Older children can add loops or conditional actions.

**Proposed implementation:** detect markers in a fixed strip, sort by position and interpret the resulting command list. A large “run” card freezes the program so hands moving cards cannot issue live commands accidentally. The browser supplies the game.

**First prototype:** four command types and a small maze. If a card is unreadable, highlight its slot instead of guessing. Physical robot control can follow after the screen version works.

**Main limitation:** defining a friendly language and debugging experience. Recognition is relatively bounded because the inputs are deliberately designed. This is an original adaptation using the marker infrastructure described above, not a published Percept product.

### 7. Stop-motion and Foley studio

**Experience:** animate LEGO or plasticine, then add your own sound effects and narration. Children create a short film instead of merely watching a camera feed.

**Proposed implementation:** take selected decoded frames from the existing camera stream, show the previous frame as a faint overlay in a browser, and assemble frames into a movie. A browser button captures frames; audio is added in a separate recording pass.

**First prototype:** capture, undo, onion-skin preview, playback at a chosen animation rate and download. Keeping originals allows later edits without repeating the shoot.

**Main limitation:** stable camera position, lighting, exposure consistency and focus matter more than AI. Test actual close-up image sharpness before designing miniature sets. This project uses the camera's demonstrated capture path without requiring real-time recognition.

### 8. Movement games and reactive art

**Experience:** freeze-dance, moving through virtual bubbles, painting with a coloured wand, or a screen creature that reacts to motion and sound.

**Precedents:** Scratch's Video Sensing extension explicitly uses camera motion to interact with projects. Charles Elwood's ABBy exhibition explored AI, ballet and visitor-created poses; the same Microsoft profile describes his Percept sign-recognition work. These demonstrate the creative direction, not an available Debian app. [Scratch Foundation](https://scratchfoundation.org/learn/learning-library/video-sensing) · [Elwood profile](https://techcommunity.microsoft.com/blog/mvp-blog/in-technology-there-is-art/3383351)

**Proposed implementation:** begin with frame differences inside a few large regions, or a coloured prop. For freeze-dance, compare motion against a room-specific baseline when the music stops. A wall display can run from a laptop; a projector is optional.

**Main limitation:** moving curtains, lighting changes and camera vibration can trigger motion. Do not label a coarse motion game as full-body tracking. Scratch's webcam input cannot directly consume the Eye's RTSP feed without integration work; reproducing the mechanic in a small web app is the simpler first route.

### 9. Cooperative escape room

**Experience:** players present the right object cards, arrange a sequence, then make a sound pattern to open the next chapter. A speaker narrates clues and a screen shows progress.

**Proposed implementation:** a small state machine combines stable marker events and, after audio qualification, simple sound events. Optional USB-connected LEDs or a microcontroller can add physical effects.

**First prototype:** three stages, adult reset, visible progress and recorded clues. Use a deliberate button/card to submit an answer rather than constantly evaluating partially arranged pieces.

**Main limitation:** puzzle design and sound false triggers. Keep physical locks theatrical; a virtual chest gives the same game mechanic with less hardware. This reuses projects 1 and 5 rather than requiring a new recognition system.

## Useful appliances and research projects

### 10. Workbench rewind and experiment notebook

**Experience:** press “keep that” after a transient fault, successful test or useful demonstration, and preserve the preceding minute plus a short period afterwards. Add a photograph, typed note or spoken annotation.

**Proposed implementation:** retain rolling H.264 segments with timestamps and save the segments covering each bookmark. MediaMTX supplies stream recording/playback; the event index, retention rules and annotation interface are custom work. [MediaMTX recording](https://mediamtx.org/docs/features/record)

**First prototype:** one camera, browser bookmark button and a clip list. Add speech only after the non-speech workflow is reliable. A later visual comparison should present before/after evidence rather than claim to explain a circuit fault automatically.

**Main limitation:** storage. The local camera test produced 78 MB in 30 seconds: about 9.4 GB/hour if that rate persisted. It is a single observation, not a guaranteed bitrate. A long archive needs external storage, bitrate control if available, or aggressive retention. Segment boundaries/keyframes may make an initial saved clip start earlier than requested.

### 11. Document camera and printed-text reader

**Experience:** put a large printed label or instruction sheet under the camera, crop the relevant region, and have it read aloud. The same setup can show a workbench to someone on a call.

**Proposed implementation:** still capture, perspective correction, Tesseract OCR and prerecorded/local speech output. Tesseract's guidance emphasises text size, noise, thresholding and deskewing; image quality should be established before trying alternative models. [Tesseract quality guidance](https://github.com/tesseract-ocr/tessdoc/blob/main/ImproveQuality.md?plain=1)

**First prototype:** one flat, well-lit, high-contrast printed card, with recognised text visible for correction before playback.

**Main limitation:** the Eye is not automatically a close-focus document scanner. Full-page fine print, handwriting and arbitrary layouts are substantially harder. A tagged picture communication board is an easier alternative to general OCR or sign-language translation.

### 12. Home Assistant voice satellite

**Experience:** room voice controls, timers and spoken responses, with the main automation server elsewhere on the LAN. Camera events can later provide context such as a deliberately presented activity card.

**Existing software:** OHF's experimental Linux Voice Assistant supports Linux ARM64, local wake-word detection, the ESPHome API and audio processing through the Linux audio stack. Its README reports Python 3.13 testing, making it more relevant to this Debian installation than old Percept Python examples. [Linux Voice Assistant](https://github.com/OHF-Voice/linux-voice-assistant)

**First prototype:** prove microphone and speaker paths; connect the satellite to an existing Home Assistant server; test a few commands and timer playback. The satellite role does not imply speech recognition runs entirely on the Percept.

**Main limitation:** full-duplex echo handling and Ear compatibility. Home Assistant distinguishes constrained Speech-to-Phrase from general Whisper transcription and reports very different compute costs on Raspberry Pi 4. Those numbers are not Percept benchmarks. Start with constrained commands, or process speech on another LAN machine. [Local Assist options](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/)

### 13. Wildlife audio/video diary

**Experience:** a daily album of feeder visitors with matching sound clips, counts and optional species suggestions. Children can correct labels and compare visits across days.

**Precedent:** the Upper Yellowstone Watershed Group documented a Percept bird-feeder project. Modern BirdNET-Go offers an existing audio-classification route, but its current hardware guide sets Raspberry Pi 4B-class hardware as the minimum and excludes Pi 3/Zero. ARM64 availability alone does not establish adequate A53 performance. [Percept feeder](https://www.upperyellowstone.org/field-notes/blog-post-title-one-xhb3m) · [BirdNET-Go hardware](https://github.com/tphakala/birdnet-go/blob/main/doc/wiki/hardware.md)

**First prototype:** motion-triggered clips and a review page, with audio recorded alongside after Ear bring-up. Run species inference on a PC initially; benchmark one lightweight classifier on the Percept only as a separate experiment.

**Main limitation:** outdoor protection, wind, acoustic quality and false classifications. An indoor speech array is not automatically a good outdoor wildlife microphone. Synchronised sound does not prove the visible bird made it. Current ARM64 release/install paths exist, but installation and speed remain untested here. [BirdNET-Go installation](https://github.com/tphakala/birdnet-go/wiki/installation)

### 14. Machine sound and motion diary

**Experience:** track one printer, fan or pump, save unusual clips, and compare today's cycle with a known-good example.

**Precedent:** Chris Jeffrey demonstrated Percept-based visual print-fault monitoring. The proposed adaptation adds sound and uses a much smaller local workflow. [Original print-monitoring project](https://techcommunity.microsoft.com/blog/iotblog/monitoring-3d-print-quality-using-azure-percept-dk/2812741)

**Proposed implementation:** fixed camera regions, sound energy/spectral features and explicit operating states. Start by detecting a changed cycle duration or unexpected silence, then gather labelled examples before using a classifier.

**First prototype:** monitor one repeating task and present suspicious clips for review. Avoid automatic machine control in this first version.

**Main limitation:** a change in sound is not a diagnosis. Placement, background activity and normal operating modes can dominate results. This is a useful experiment logger before it is a credible fault detector.

### 15. LEGO or microcontroller robot controller

**Experience:** a robot responds to printed road signs, follows a marked route, or acts out a sequence of command cards.

**Precedents:** Goran Vuksic's Perceptmobile used a LEGO Boost chassis and cone detection; Ron Dagdag published a Percept-to-Arduino integration. Their original Azure components would need replacing. [Perceptmobile and demonstration](https://www.hackster.io/gvuksic/perceptmobile-azure-percept-obstacle-avoidance-lego-car-1cde4f) · [Perceptmobile code](https://github.com/gvuksic/PerceptMobile) · [Arduino source](https://github.com/rondagdag/arduino-percept)

**Proposed implementation:** let the Percept interpret visible signs and send high-level instructions. A compatible hub or microcontroller handles motors and a stop-on-disconnect watchdog. Pybricks documents BLE communication between a computer and a hub running its firmware, but exact hub compatibility and firmware installation need checking. [Pybricks communication](https://pybricks.com/projects/tutorials/wireless/hub-to-device/pc-communication/)

**First prototype:** keep the powered Percept stationary above a tabletop; command a small robot below. This avoids carrying the DK's power supply and cables on the vehicle.

**Main limitation:** extra hardware, pairing/protocol work and control latency. Bluetooth scanning on this board is proven; robot communication is not. Do not substitute the source article's unverified power claim for the correct supply for this unit.

### 16. Conference or document-camera accessory

**Experience:** use the Percept as an overhead workbench camera, with a PC running Teams or another meeting app. Add audio only after an end-to-end test.

**Proposed implementation:** bridge the RTSP stream into suitable capture software on the PC, then expose it as a virtual camera. An audio route is separate: a virtual camera generally does not transport microphone audio. Begin with the meeting PC's existing microphone/speaker while qualifying the Ear path.

**First prototype:** a remote participant confirms the video is useful and measures delay. If adding Ear audio, test synchronisation and whether the remote speaker output feeds back into capture.

**Main limitation:** USB webcam emulation is not established on this board; use the network first. A browser viewing RTSP through a bridge is also not automatically a camera device selectable in Teams. A standalone terminal adds display and browser performance questions. Official Teams Rooms uses dedicated certified platforms. [Teams web](https://learn.microsoft.com/microsoftteams/teams-client-web) · [Teams device platform](https://learn.microsoft.com/microsoftteams/rooms/security)

## Actual Percept precedents worth exploring

These are historical demonstrations, not verified applications for the current Debian installation. Original author/project material is prioritised over collections of generic IoT ideas.

| Project | What the evidence establishes | What carries forward |
|---|---|---|
| [Perceptmobile](https://github.com/gvuksic/PerceptMobile) | Published LEGO obstacle-avoidance project and source | Visual events can drive a toy robot; replace cloud routing |
| [PokerBot](https://github.com/microsoft/MTC_PokerBot) | Card-suit model, game logic and a cloud-backed physical-card game | Camera-readable physical game pieces; not a ready offline game |
| [ABBy / Elwood profile](https://techcommunity.microsoft.com/blog/mvp-blog/in-technology-there-is-art/3383351) | Interactive art, audience-created poses, and Percept sign-recognition work | Creative movement interaction; not proof of general emotion or sign-language understanding |
| [Percept bird feeder](https://www.upperyellowstone.org/field-notes/blog-post-title-one-xhb3m) | Documented feeder and species-model experiment | Family nature diary; current species accuracy is unverified |
| [Pete Codes Audio project](https://www.petecodes.co.uk/azure-percept-audio-webhooks-azure-functions-iot-hub-raspberry-pi-and-home-automation/) | Voice commands controlling a Raspberry Pi relay through Azure | Voice-to-action interaction; speech/cloud implementation needs replacement |
| [Print-fault monitoring](https://techcommunity.microsoft.com/blog/iotblog/monitoring-3d-print-quality-using-azure-percept-dk/2812741) | Detailed vision-to-printer-action prototype | Fixed-scene monitoring and event review |
| [Drone inspection](https://techcommunity.microsoft.com/blog/iotblog/rapidly-equip-a-drone-with-ai-using-the-azure-percept-dk/2779509) | Percept mounted to a drone for roof-defect inspection | Evidence of a mobile vision application; not an easy first build |
| [LEGO excavator / HoloLens](https://techcommunity.microsoft.com/blog/iotblog/transform-your-field-service-management-with-azure-percept-and-hololens/3167006) | Marble-colour detection connected to a digital twin and visualisation | Simple physical objects controlling a richer on-screen model |
| [Microsoft reference solutions](https://github.com/microsoft/Azure-Percept-Reference-Solutions) | Archived examples for counting, OCR, hand hygiene and voice inventory | Architecture and source references; old service deployment instructions are not reusable unchanged |

The wider search did find interactive art and gesture examples beyond the earlier shortlist. It did not establish an existing maintained Percept musical-instrument distribution or a ready-to-install children's games suite.

## A practical shared software foundation

These are proposed design choices, not new features already present on the board.

1. **Retain the existing Eye runtime as the camera service.** Use its mount-isolated wrapper. Consume the H.264 stream, decode via a tested path, resize frames for analysis and drop stale frames instead of accumulating a queue. Compare against the documented 15-fps MJPEG option if needed; delivered rate is not a latency measurement.
2. **Keep new application code in normal Debian userspace.** OpenCV trixie has ARM64 Python packages, so marker and colour processing need not be built inside the legacy camera environment. Those packages do not replace the proprietary capture runtime. [Debian OpenCV](https://packages.debian.org/trixie/python3-opencv)
3. **Use one small visual vocabulary.** Large printed markers and coloured regions are appropriate first inputs. Build a calibration view, stability filtering and clear “lost target” behaviour. A fixed tabletop can be mapped with a planar transform; there is no need to claim depth sensing.
4. **Send semantic events to a local web interface.** For example, card identity and zone, normalised movement, record request or bookmark. The browser displays the game and can play sound. It can operate over the local network with locally hosted assets, without Azure or internet access after setup. No live camera preview is required for a sequencer.
5. **Separate musical timing from frame arrival.** The audio engine schedules notes, and camera events change parameters or the next beat/bar. For local audio, evaluate Pure Data or FluidSynth after playback is proven. For browser audio, use Tone.js and an explicit start-audio control.
6. **Add the Ear as an independent input service after qualification.** Begin with mono recording and level measurement. Share this stream between applications rather than having several processes compete for a hardware endpoint. More advanced voice analysis is optional.
7. **Use the PC selectively.** Bird identification, general transcription, image-language models and video-call software can run elsewhere while the Percept remains the physical sensor/controller. This still works without Azure; it is not fully standalone.

MediaMTX is a candidate for recording and browser preview. Its protocol conversion does not imply codec conversion: WebRTC playback depends on the actual H.264 stream and browser, and H.264 with B-frames needs special attention. Avoid designing a project around an untested zero-transcode browser path. [MediaMTX overview](https://mediamtx.org/docs/kickoff/introduction) · [Browser playback](https://mediamtx.org/docs/read/web-browsers) · [Codec constraints](https://mediamtx.org/docs/features/webrtc-specific-features)

## The qualification work that changes the choices

These are proposed future tests, not commands executed in this research.

| Test | Evidence to collect | Decisions it unlocks |
|---|---|---|
| Ear enumeration and software access | Firmware identity, available ALSA/PipeWire endpoints, formats and channel counts | Whether current audio hardware can support any audio-based project without further recovery work |
| Short recording and playback | A recording actually contains clear speech/sounds; playback works; record/play interaction | Sampler, monster, narration, voice satellite |
| Signal suitability | Compare quiet speech, hums, claps and environmental sounds; observe clipping/noise processing | Whether the speech-oriented input is also useful for instruments or wildlife |
| Camera control latency | Film a visible change and the application response using an independent reference; inspect queues | Whether smooth control is responsive enough; do not infer latency from fps |
| Marker reliability | Detect several large tags on the intended table in real lighting, with hands briefly covering them | Tabletop, cards, programming games |
| Sustained application run | CPU/RAM, backlog, audio underruns, temperature and recovery after disconnection | Reliable interactive appliance rather than a short demo |
| Single-model benchmark | Real processing time and memory on this unit, with the camera workload active | Optional Vosk/Piper/BirdNET/custom vision work |

The ASUS retirement guide identifies a no-auth audio container, and the community Python library demonstrates historical WAV recording but includes obsolete authentication assumptions and old Python support. Neither proves that this newly acquired Ear currently works under Debian. Do not automatically flash it or assume four independently available microphone channels. [ASUS retirement guide](https://dlcdnets.asus.com/pub/ASUS/mb/Embedded_IPC/DKSC-101/Unsupported_SoM_Update_Azure_Percept_DK_Camera_and_Audio_SoMs.pdf?model=AS-101) · [Community audio library](https://github.com/christian-vorhemus/azure-percept-py)

For a small custom spoken-command vocabulary, Vosk is another candidate: upstream explicitly supports ARM64 and small offline models. Its older installation documentation is not a guarantee of trouble-free Python 3.13 packaging. Validate packaging and measured recognition before choosing it. Prerecorded speech avoids that dependency for most children's projects. [Vosk installation](https://alphacephei.com/vosk/install) · [Vosk project](https://github.com/alphacep/vosk-api)

## Directions to defer

- **Modern models “because Myriad is present.”** Intel removed MYRIAD support from OpenVINO 2023.0; Microsoft's camera integration has its own older requirements. An old compatible model is possible research, but neither current OpenVINO nor an OAK/DepthAI example is automatically a Percept solution. [Intel support history](https://docs.openvino.ai/2023.3/openvino_docs_OV_UG_supported_plugins_Supported_Devices.html) · [Microsoft toolchain constraints](https://github.com/microsoft/azure-percept-advanced-development/blob/main/README.md)
- **Full-body tracking, unrestricted sign-language translation and arbitrary toy recognition as a first milestone.** Narrow gestures or tagged props are much easier to validate. Historical demos establish specific demonstrations, not general recognition quality.
- **Precision air drums and instant live voice effects.** Camera delay, audio buffering and feedback must first be measured. A loop arranger or record-then-play sampler is the stronger starting point.
- **Acoustic direction finding or beamforming.** Four physical microphones do not establish accessible raw synchronised channels. A linear array also brings geometric ambiguities that would need separate evaluation.
- **A full local multimodal conversational companion.** Use a deterministic character with recorded lines, or place larger models on a PC. The CPU and Myriad evidence does not support promises of responsive modern vision-language inference.
- **Standalone Teams Rooms or a plug-in USB conference bar.** Browser, display, echo cancellation, USB role and certification issues make these disproportionately difficult relative to a network document camera.
- **A large multi-camera AI recorder on the board.** Start with one encoded stream and bounded storage. Current Frigate detector documentation does not establish a supported Percept Myriad path. [Frigate detector source documentation](https://github.com/blakeblackshear/frigate/blob/dev/docs/docs/configuration/object_detectors.md)

## Suggested order

**First:** make a four-card musical tabletop using the working camera and a browser's audio output. It gives a playable result even if Ear bring-up takes time.

**Second:** qualify the Ear, then add short sample recording. The same cards become a sound-catching game, a story theatre or a beat arranger.

**Third:** choose a second application based on what was enjoyable: stop-motion for making films, coding cards for learning, workbench rewind for practical use, or a Home Assistant satellite for a daily appliance.

The most valuable reusable work is the dependable camera/audio input layer and a small physical vocabulary. It gives this hardware several purposes while keeping the legacy vendor runtime confined to the job it already performs.
