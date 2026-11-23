"""Controllers: own the model, the plots and playback, and hand frames to a view

`base.Controller` is view independent. It builds a `Source` and a `PlotSet` over the model, applies the launch layout,
and does everything a view asks for: add, remove, move, retype and link plots, change settings and markers, save and
load layouts, export a plot's latest frame, record, retune, seek. A view's controller subclasses it and only says what
it can draw (`FEATURES`, plots needing others are not offered) and what to do with frames:

    class Controller(base.Controller):
        FEATURES = {LINE, SCATTER, IMAGE}
        def deliver(self, frames, status): ...   # {plot id: Frame}, once per block

`step()` reads one block, ticks the source, renders every plot and delivers. Playback is either threaded
(`start_stream`, for event driven views: web, tk) or driven by the view calling `tick()` (console), paced to `--show`
ms per frame. Everything touching the model or plots holds `lock`.

| Package | View |
|---|---|
| `controller.WEB` | FastAPI routes and a websocket; frames go to the browser as binary messages (`controller.WEB.wire`) |
| `controller.tkGUI` | matplotlib figures in tk panes (`controller.tkGUI.plot.PlotPane` draws any Frame), settings panels |
| `controller.CUI` | a command line (`help` lists the commands), frames drawn as text by `view.CUI.draw` |

`controller.GetController(view, sink)` picks one; `ControllerArgs` registers its options.
"""
