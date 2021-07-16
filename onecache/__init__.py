"""Main module."""

from argparse import ArgumentParser
from configparser import ConfigParser

from onecache_utils import get_logger


def get_arguments():
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', default='./config.ini')
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser.parse_args()


def main():
    """Start script."""
    args = get_arguments()
    config = ConfigParser()
    config.add_section('logging')
    config.read(args.config)
    logger, uuid = get_logger(config, args.debug, args.verbose)
    logger.info('Starting script...')


if __name__ == '__main__':
    main()
