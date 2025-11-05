"""Initialize CUI Controller"""
from ..base import Controller as _Controller

from ...view.cui import View as CUI
from ...model.model import Model

from .plot_base import PSD

def define_args(parser):
    ctrl = parser.add_argument_group("CUI")
    return ctrl

class Controller(_Controller):
    """CUI Controller"""
    def __init__(self, model: Model, view: CUI, **kwargs):
        super().__init__(model, view)
        self.view: CUI = self.view # type hints
        self.view.menu = self.menu
        self.psd = PSD(self)

    def show_help(self, ind=2):
        print(" "*ind + "h|help  .  .  .  .  .  .  .  : view this message")
        print(" "*ind + "q|quit|exit   .  .  .  .  .  : exit")
        print(" "*ind + "c|config   .  .  .  .  .  .  : show/edit configuration")
        self.cmd_config([], ind=ind+2)
        print(" "*ind + "s|state .  .  .  .  .  .  .  : change state")
        self.cmd_state([], ind=ind+2)
        print(" "*ind + "v|view")
        self.cmd_view([], ind=ind+2)


    def menu(self):
        args = input("pyspecan > ").split(" ")
        if args[0] in ("h", "help"):
            self.show_help()
        elif args[0] in ("q", "quit", "exit"):
            self.view.running = False
        elif args[0] in ("c", "config", "configure"):
            self.cmd_config(args[1:])
        elif args[0] in ("v", "view"):
            self.cmd_view(args[1:])

    def cmd_config(self, args, ind=4):
        def show_help():
            print(" "*ind + "s|show   .  .  .  .  .  .  : view args")
            print(" "*ind + "f|path <path>  .  .  .  .  : set sample rate")
            print(" "*ind + "d|fmt <fmt> .  .  .  .  .  : set sample rate")
            print(" "*ind + "")
            print(" "*ind + "fs <Fs>  .  .  .  .  .  .  : set sample rate")
            print(" "*ind + "cf <cf>  .  .  .  .  .  .  : set center frequency")
            print(" "*ind + "n|nfft <nfft>  .  .  .  .  : set sample rate")
            print(" "*ind + "st|sweep_time <sweep>   .  : set sample rate")

        if len(args) == 0 or args[0] in ("h", "help"):
            show_help()
            return
        if args[0] in ("s", "show"):
            print(" "*ind + f"  {self.model.cur_time():.2f}s/{self.model.tot_time():.2f}s")
            print(" "*ind + "  Reader:")
            self.model.reader.show(ind+2)

            print(f"  Fs: {self.model.Fs} | cf: {self.model.cf}")
            print(f"  nfft: {self.model.nfft} | Sweep time: {self.model.sweep_time}")
        elif args[0] in ("f", "path"):
            if len(args) == 2:
                self.model.reader.path = args[1]
                print(" "*ind + str(self.model.reader.path))
        elif args[0] in ("d", "fmt") and len(args) == 2:
            self.model.reader.fmt = args[1]
            print(" "*ind + str(self.model.reader.fmt))
        elif args[0] in ("fs",) and len(args) == 2:
            self.model.Fs = args[1]
            print(" "*ind + str(self.model.Fs))
        elif args[0] in ("cf",) and len(args) == 2:
            self.model.cf = args[1]
            print(" "*ind + str(self.model.cf))
        elif args[0] in ("n", "nfft") and len(args) == 2:
            self.model.nfft = args[1]
            print(" "*ind + str(self.model.nfft))
        elif args[0] in ("st", "sweep_time") and len(args) == 2:
            self.model.sweep_time = args[1]
            print(" "*ind + str(self.model.sweep_time))

    def cmd_state(self, args, ind=4):
        def show_help():
            print(" "*ind + "n|next   .  .  .  .  .  .  : advance to next block")
            print(" "*ind + "p|prev   .  .  .  .  .  .  : reverse to previous block")

        if len(args) == 0 or args[0] in ("h", "help"):
            show_help()
            return
        elif args[0] in ("n", "next"):
            valid = self.model.next()
            print(" "*ind + f"{valid}")
        elif args[0] in ("p", "prev"):
            valid = self.model.prev()
            print(" "*ind + f"{valid}")

    def cmd_view(self, args, ind=4):
        def show_help():
            print(" "*ind + "p|psd .  .  .  .  .  .  .  : view psd")

        if len(args) == 0 or args[0] in ("h", "help"):
            show_help()
            return
        elif args[0] in ("p", "psd"):
            self.psd.plot(self.model.f, self.model.psd())
            self.psd.show()
