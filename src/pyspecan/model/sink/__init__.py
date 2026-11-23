"""Sinks: the sample sources a `Model` reads from, one block per `next(count)`

`Sink` is the base: sample rate and center frequency (`Frequency`), the last block (`samples`, complex64), whether it
follows the one before (`contiguous`), its place (`block_index`, `block_time`), and what views show about the source
(`status`, `live_status`, `stream_status`). `SinkFile` reads files (pysdrlib `File`), `SinkLive` radios (pysdrlib
`Device`, local or on a server), `SinkTcpIq` TCP IQ streams (pysdrlib `tcpiq`). Each module's `args_*` adds that
sink's command line options.
"""
from .file import SinkFile, args_file
from .live import SinkLive, args_live
from .sink import Sink
from .tcpiq import SinkTcpIq, args_tcpiq
