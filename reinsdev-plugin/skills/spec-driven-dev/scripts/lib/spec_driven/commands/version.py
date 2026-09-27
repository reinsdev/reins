from .. import VERSION


def register(sub):
    sub.add_parser("version", help="显示版本")


def run(a) -> int:
    print(VERSION)
    return 0
