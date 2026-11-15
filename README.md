# Planet X and SPHEREx Project (Team Universales)

Web application that animates SPHEREx telescope images of a region of the sky,
based on given coordinates, to help detect objects that change position.

[Link to the hackathon challenge](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/?tab=details)

## What problem it solves

SPHEREx observes the entire sky and publishes images every week: there are too many to
review manually. A moving object (an asteroid, a comet, a nearby star)
looks like just another star in a single image, but when comparing the same area across
multiple dates, it "jumps" while fixed stars stay still. This tool
does the work of downloading, aligning, and animating the images so anyone
can spot it, without installing astronomical software.

## Features

- Choose a region of the sky by RA and Dec (in degrees) and its size.
- Choose the SPHEREx detector band (D1 to D6).
- Image animation in chronological order, with blink interval, zoom,
  brightness range, and pixel value inversion.
- Frame-by-frame view with the date and wavelength of each image.
- "Difference" mode: subtracts static elements so only what changes stands out.
- Candidate list (position per frame) exportable to CSV.
- Overlay of known Gaia DR3 stars (with real data).
- Demo mode with synthetic data, without an internet connection.

## How to use it

1. Enter the coordinates, or leave the example ones (the M101 galaxy).
2. Check "Use real IRSA data" to download the SPHEREx images.
3. In the "Animation" tab, watch how the region moves; in "Frame by frame", review
   each date.
4. Switch to "Difference" mode so what moves stands out, and check the candidate
   table.

## Installation

```bash
pip install -r requirements.txt
streamlit run app.py
```

With uv: `uv sync` and then `uv run streamlit run app.py`.

## How it works

| File | What it does |
| --- | --- |
| `data.py` | Searches IRSA for observations covering the region and downloads the cutouts (with caching and retries) |
| `process.py` | Reads the FITS files, masks bad pixels, and aligns all frames to the same coordinate system |
| `detect.py` | Normalizes, calculates the difference image, and finds candidates |
| `catalogs.py` | Gaia DR3 stars and their position in the image |
| `animate.py` | Converts the image cube into frames and a GIF |
| `fake_data.py` | Synthetic data to develop and test without internet |
| `app.py` | Web interface (Streamlit) |

## Tests

```bash
pytest -q
```

The tests do not require internet: they simulate IRSA with a local server and mock FITS
cutouts, and verify that they download, align, and detect the moving object.

## Data and sources

- Images: SPHEREx, [IRSA (NASA/IPAC)](https://irsa.ipac.caltech.edu/Missions/spherex.html) archive.
  The query and cutouts follow the
  [official cutouts tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts).
  TO DO: copy here the acknowledgement text requested by IRSA on its page.
- Known stars: [Gaia DR3](https://archive.stsci.edu/missions-and-data/gaia).
- Interface reference: [WiseView](http://byw.tools/wiseview).

## Known limitations

- Each SPHEREx image has a different wavelength depending on the pixel, so the
  same star may look brighter or dimmer between frames and leave residuals in
  Difference mode. That is why the wavelength of each frame is shown and a
  single detector band is chosen.
- The bad pixel mask uses the `FLAGS` bit list from the SPXQuery package;
  it still needs to be confirmed with Table 16 of the SPHEREx Explanatory Supplement.
- The blink is a GIF that is regenerated every time a control is changed, so it takes a little while.
- Object discovery is a visual aid: candidates must be manually reviewed.
- TO DO: test with real IRSA data and note here what is found.

## Use of AI

We used AI as support for the code, as permitted by the organizers.

- **The idea and scope** stem from the official "Planet X and SPHEREx" challenge and WiseView,
  the reference provided by the organizers.
- **Planning:** the work plan, stages, and contracts between modules were
  drafted with Claude (Anthropic); the team reviewed and adapted them.
- **Code:** Claude wrote reference examples for `animate.py`, `app.py`,
  `catalogs.py`, `detect.py`, `fake_data.py`, and `process.py`, and the versions of `data.py`,
  `process.py`, and the tests we used, based on the official IRSA tutorial.
 
All integrated modules were tested and validated:
- The M101 observation run worked, with masked pixels and data-free corners.
