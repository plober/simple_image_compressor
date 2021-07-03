# Simple Image Compressor

Simple utility to compress images on a given path, with recursion.
It uses multiple processes to consume the source directories queue.
Does not preserve image metadata.
See the [settings](settings.json) file.

**Usage**: `simple_image_compressor.py [-h] [-v {0,1,2,3}] [-s] [-t] [-n] path [path ...]`

**Positional arguments**:
`path`            paths separated with spaces (paths with spaces must be quoted)

**Optional arguments**:
`-h, --help`      show the help message and exit
`-v {0,1,2,3}`    verbosity level: 0=log file, 1=print dirs, 2=print files, 3=print json
`-s`              soft compression: doesn't resize, just compresses up to 80% quality
`-t`              temp output: doesn't replace source images, instead saves compressed images to %temp%
`-n`              no exceptions: process directories even if they're in the exceptions list

> PS: First project in Python.