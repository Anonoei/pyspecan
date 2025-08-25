import datetime as dt

def split_td(td: dt.timedelta):
    s = td.total_seconds()
    hrs, remainder = divmod(s, 3600)
    mins, secs = divmod(remainder, 60)
    secs, ms = divmod(secs, 1)
    return int(hrs), int(mins), int(secs), int(ms*1000)

def strfmt_td(td: dt.timedelta):
    ch, cm, csec, cms = split_td(td)
    return f"{ch:03d}:{cm:02d}:{csec:02d}.{cms:03d}"
