# FinancialAcc

## Local setup

Use Python 3.13 for this project.

Python 3.14 currently breaks `python-bidi==0.6.6` during installation because its
PyO3 build dependency only supports up to Python 3.13. When that happens, `pip`
falls back to building native packages from source, which is why Pillow can also
fail with missing `jpeg` headers.

### Recommended steps

```bash
cd Finacc
rm -rf ../venv
python3.13 -m venv ../venv
../venv/bin/pip install --upgrade pip setuptools wheel
../venv/bin/pip install -r requirements.txt
```

### Notes

- If `python3.13` is not installed, install it first and recreate the virtualenv.
- Avoid Python 3.14 for now unless `python-bidi` is upgraded to a version that
  supports it.
- If you still force a source build of Pillow, you may need system JPEG libraries
  installed, but on Python 3.13 `pip` should normally download a prebuilt wheel.
