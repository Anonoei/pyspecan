import argparse

from ..obj import Frequency

def update_register(parser: argparse.ArgumentParser):
    parser.register("type", "frequency", Frequency.get)

def get_group(
        parser: argparse.ArgumentParser,
        title: str, description=None, **kwargs):
    """Runs parser.add_argument_group, getting existing group if it has the same name"""
    if parser._action_groups:
        for group in parser._action_groups:
            if group.title == title:
                return group
    return parser.add_argument_group(title, description, **kwargs)
