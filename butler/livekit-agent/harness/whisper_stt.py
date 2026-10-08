"""Local Whisper as a drop-in for groq.STT, so the harness hears real words."""
import asyncio, logging
import numpy as np
from faster_whisper import WhisperModel
from livekit.agents import stt, utils
from livekit.agents.stt import STTCapabilities, SpeechData, SpeechEvent, SpeechEventType

logger = logging.getLogger("whisper-stt")
_model = None


def model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _model


class WhisperSTT(stt.STT):
    def __init__(self, **_):
        super().__init__(capabilities=STTCapabilities(streaming=False, interim_results=False))

    async def _recognize_impl(self, buffer, *, language=None, conn_options=None) -> SpeechEvent:
        frame = utils.merge_frames(buffer)
        pcm = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
        if frame.num_channels > 1:
            pcm = pcm.reshape(-1, frame.num_channels).mean(axis=1)
        if frame.sample_rate != 16000:
            n = int(len(pcm) * 16000 / frame.sample_rate)
            pcm = np.interp(np.linspace(0, len(pcm), n, endpoint=False), np.arange(len(pcm)), pcm).astype(np.float32)
        segments = await asyncio.to_thread(lambda: list(model().transcribe(pcm, language="en", beam_size=1)[0]))
        text = " ".join(s.text.strip() for s in segments).strip()
        print(f"STT segment {len(pcm) / 16000:.2f}s: {text!r}", flush=True)
        return SpeechEvent(type=SpeechEventType.FINAL_TRANSCRIPT, alternatives=[SpeechData(text=text, language="en")])
