"""Create a CUI view"""

from .base import View as _View

class View(_View):
    """Parent CUI view class"""
    def __init__(self):
        self.running = True

    def mainloop(self):
        while self.running:
            try:
                self.menu()
            except KeyboardInterrupt:
                pass

    def show_help(self):
        print("  h|help  .  .  .  .  .  .  .  : view this message")
        print("  q|quit|exit   .  .  .  .  .  : exit")
        print("  a|args  .  .  .  .  .  .  .  : show/edit arguments")
        self.cmd_args([])
        print("  v|view")
        self.cmd_view([])


    def menu(self):
        args = input("pyspecan > ").split(" ")
        if args[0] in ("h", "help"):
            self.show_help()
        elif args[0] in ("q", "quit", "exit"):
            self.running = False
        elif args[0] in ("a", "args"):
            self.cmd_args(args[1:])
        elif args[0] in ("v", "view"):
            self.cmd_view(args[1:])

    def cmd_args(self, args):
        def show_help():
            print("      s|show .  .  .  .  .  .  : view args")
            print("      fs <fs>   .  .  .  .  .  .  : set sample rate")
            print("      cf <cf>   .  .  .  .  .  .  : set center frequency")

        if len(args) == 0 or args[0] in ("h", "help"):
            show_help()
            return
        if args[0] in ("s", "show"):
            print(f"  {self.view.model.cur_time():.2f}s/{self.view.model.tot_time():.2f}s")
            print("  Reader:")
            self.view.model.reader.show(4)
            print(f"  Fs: {self.view.model.Fs} | cf: {self.view.model.cf}")
        elif args[0] in ("fs",) and len(args) == 2:
            self.view.model.Fs = int(args[1])
        elif args[0] in ("cf",) and len(args) == 2:
            self.view.model.cf = int(args[1])

    def cmd_view(self, args):
        def show_help():
            print("      p|psd  .  .  .  .  .  .  : view psd")

        if len(args) == 0 or args[0] in ("h", "help"):
            show_help()
            return
