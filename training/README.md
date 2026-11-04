# PHAEMA training courses

Interactive e-learning for five roles (estates surveyor, finance officer, maintenance and compliance, system
administrator, viewer and contributor). Each module has walkthrough steps with the relevant part of the real screen
highlighted, a "try it yourself" exercise on the demonstration data, and a short quiz. Progress is kept in the
learner's browser.

- Content: `course.py`. Build: `python3 training/build.py`, which writes `static/training/index.html`.
- PHAEMA serves it at `/static/training/index.html`, linked from Help, Training courses.
- Screenshots: `static/training/img/<module>-<step>.jpg`, with highlight boxes in `boxes.json`. They were captured
  from the demonstration data with the Classic style; re-capture them when a screen changes.
