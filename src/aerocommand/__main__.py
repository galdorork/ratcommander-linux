"""Start the app. ``--demo`` uses a simulated mouse and never touches hardware."""

from __future__ import annotations

import argparse
import sys

from .backend import DisabledBackend, FakeBackend, FakeScenario


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ratcommander", description=__doc__)
    parser.add_argument("--layout", choices=("auto", "kde", "gnome"), default="auto",
                        help="desktop layout (default: detect the desktop session)")
    parser.add_argument("--demo", action="store_true",
                        help="use a simulated mouse; nothing is written to hardware")
    parser.add_argument("--demo-scenario", choices=[s.value for s in FakeScenario],
                        default=FakeScenario.SUCCESS.value,
                        help="simulated outcome in demo mode (default: success)")
    parser.add_argument("--demo-delay", type=float, default=1.5,
                        help="seconds a simulated write takes (default: 1.5)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    from PySide6.QtWidgets import QApplication

    from .controller import Controller, ThreadRunner
    from .profiles import ProfileStore
    from .window import APP_NAME, MainWindow, UiDispatcher

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("ratcommander")
    if args.demo:
        backend = FakeBackend(FakeScenario(args.demo_scenario), delay=args.demo_delay)
        backend.readable = True
    else:
        try:
            from .hid_backend import HidBackend
            backend = HidBackend(backup_dir=ProfileStore().dir / "backups")
        except ImportError:
            backend = DisabledBackend()
    runner = ThreadRunner(UiDispatcher())
    controller = Controller(ProfileStore(), backend, runner)
    window = MainWindow(controller, demo=args.demo, layout=args.layout)
    controller.start()
    window.resize(1180, 680)
    window.show()
    code = app.exec()
    runner.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
