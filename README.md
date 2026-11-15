# Planet X and SPHEREx Project (Team Universales)

Web application that animates SPHEREx telescope images of a sky region from a set of coordinates to help detect moving objects like asteroids or comets. 

[Link to the hackathon challenge](https://spaceappschallenge.org)

## What Problem It Solves

Automates downloading, aligning, and animating weekly SPHEREx sky images to spot moving objects that "jump" across frames while stationary stars remain fixed.

## Features

- **Region selection:** Choose sky coordinates (RA and Dec) and size, plus SPHEREx detector band (D1–D6).
- **Visualization:** Chronological animation with adjustable blink interval, zoom, brightness, pixel inversion, and a frame-by-frame view.
- **Analysis:** "Difference" mode to subtract static backgrounds, CSV export for candidate objects, and Gaia DR3 star overlays.
- **Mode:** Includes an offline synthetic data demo mode.

## How to Use

1. Enter coordinates or keep the default M101 galaxy example.
2. Check "Use real data from IRSA" for live downloads.
3. Use the "Animation" or "Frame by frame" tabs to review shift patterns.
4. Switch to "Difference" mode to isolate moving objects and check the candidate list.

## Installation & Testing

```bash
pip install -r requirements.txt
streamlit run app.py
```
*(Or using uv: `uv sync` and `uv run streamlit run app.py`)*. Run tests via `pytest -q`.

## How It Works

- `data.py`: Queries and downloads IRSA observations with caching.
- `process.py`: Reads FITS files, masks bad pixels, and aligns coordinates.
- `detect.py`: Normalizes frames and computes difference images for candidates.
- `catalogs.py` & `animate.py`: Fetches Gaia DR3 stars and generates GIFs.
- `fake_data.py` & `app.py`: Generates synthetic offline data and runs the Streamlit interface.

## Data, Sources, and Limitations

- **Sources:** SPHEREx data via [IRSA (NASA/IPAC)](https://caltech.edu) following the [official tutorial](https://github.io), plus [Gaia DR3](https://stsci.edu) and [WiseView](http://byw.tools).
  - *Acknowledgement:* Data products utilized from SPHEREx (JPL/Caltech, NASA-funded). For full acknowledgement details, please consult {Link: NASA IPAC IRSA https://caltech.edu}.
- **Limitations:** Wavelength variations across pixels can leave residuals in Difference mode; bad-pixel masks require verification; GIF regeneration causes slight delays; and candidates need manual verification.

## Use of AI

AI was utilized as a permitted coding and planning assistant (via Claude/Anthropic) to help structure module contracts, draft initial code examples based on IRSA tutorials, and assist with debugging, subject to team review.

*Note: Remember to replace the remaining **TO DO** placeholders in your repository before final submission.*
