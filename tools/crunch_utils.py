import os
import re

def parse_filename(filename, suffix):
    dir, file = os.path.split(filename)

    mesh = "unknown"

    if "ambient" in dir:
        mesh = "ambient"
    elif "linkerd" in dir:
        mesh = "linkerd"

    regex = r"([^-]+)-(\d+)-" + suffix

    # print(f"Parsing {filename} with regex {regex}")
    match = re.match(regex, file)

    if match:
        rps = int(match.group(1))
        seq = match.group(2)
    else:
        raise Exception("Unrecognized file name %s" % file)

    return (mesh, rps, seq)
