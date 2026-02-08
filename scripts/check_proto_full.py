import sys
from ctrader_open_api.messages import OpenApiMessages_pb2 as msg
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as mdl
from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as common

with open("proto_dump.txt", "w") as f:
    f.write("MSG:\n")
    f.write(str([x for x in dir(msg) if "Proto" in x]))
    f.write("\n\nMDL:\n")
    f.write(str([x for x in dir(mdl) if "Proto" in x]))
    f.write("\n\nCOMMON:\n")
    f.write(str([x for x in dir(common) if "Proto" in x]))
