# Integration test fixtures

`test_integration.py` (marked `integration`, skipped by default) expects four
small face JPEGs here, supplied by you with consent. Keep each < 200 KB.

| File | Content |
|------|---------|
| `same_person_1.jpg` | A consenting person. |
| `same_person_2.jpg` | A second photo of the **same** person. |
| `different_person.jpg` | A **different** person. |
| `printed_photo.jpg` | A photo of a printed/screen face (spoof case). |

Run model-backed tests (requires buffalo_l pack + `models/minifasnet.onnx`,
see `docs/operations.md`):

```bash
FACECORE_RUN_INTEGRATION=1 pytest facecore/tests/test_integration.py -v
```
