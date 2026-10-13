# Third-party notices

SpeakTrace original code is MIT licensed. The application does not relicense third-party software, model weights or source recordings.

- **wav2vec2-base-960h**, Meta/Facebook, Apache-2.0; pinned revision in `.models/wav2vec2-base-960h/speaktrace-model.json`. https://huggingface.co/facebook/wav2vec2-base-960h
- **PyTorch**, BSD-style; https://github.com/pytorch/pytorch/blob/main/LICENSE
- **Transformers**, Apache-2.0; https://github.com/huggingface/transformers/blob/main/LICENSE
- **NumPy / SciPy**, BSD; https://numpy.org/ and https://scipy.org/
- **librosa**, ISC; used for pitch-preserving time-stretching in dataset construction. https://librosa.org/
- **SoundFile**, BSD-style Python wrapper with libsndfile's own license; https://python-soundfile.readthedocs.io/
- **FastAPI / Uvicorn**, their upstream MIT/BSD licenses; https://fastapi.tiangolo.com/ and https://www.uvicorn.org/

Pretrained-model background: Baevski et al., *wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations* (2020), https://arxiv.org/abs/2006.11477. CTC alignment follows the standard blank-interleaved dynamic-programming formulation; see https://docs.pytorch.org/audio/stable/tutorials/forced_alignment_tutorial.html.

The archive recordings are identified in `data/sources.json` with recording-level rights evidence. Public-domain statements are the archives' stated U.S. status, not a claim about every copy of a speech or every jurisdiction. Modified examples are clearly labelled educational transformations. They do not represent the original speaker's actual delivery.

External source audio, model weights, virtual environments, full raw downloads and caches are excluded from the source ZIP except for the short documented dataset audio required by the contest. Model weights download separately with their upstream license metadata.
