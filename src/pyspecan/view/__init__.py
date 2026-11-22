"""Views: the window, page or terminal a frontend draws in

`view.GetView(View, Sink)` picks one. A view only runs the toolkit's main loop (`base.View.mainloop`); what goes on
screen is decided by its controller (`pyspecan.controller`), which draws the plots' `Frame`s.

| Package | Frontend | Needs |
|---|---|---|
| `view.WEB` | a FastAPI app served by uvicorn; the page (`static/app.js`) draws frames on canvases, 3D included | `pyspecan[web]` |
| `view.tkGUI` | a tk window with matplotlib figures, one panel per sink | `pyspecan[tk]` |
| `view.CUI` | the terminal: braille traces, half-block images (`view.CUI.draw`) | nothing |
"""
