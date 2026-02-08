import sys
try:
    from ctrader_open_api.messages import OpenApiMessages_pb2 as msg
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as mdl
    from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as common
except ImportError:
    print("Biblioteca ctrader_open_api não encontrada.")
    sys.exit(1)

def check(name, module):
    if hasattr(module, name):
        print(f"FOUND: {name} in {module.__name__}")
        return True
    return False

print("Searching for ProtoOAPingReq...")
found = False
for m in [msg, mdl, common]:
    if check("ProtoOAPingReq", m):
        found = True

if not found:
    print("NOT FOUND in any module.")
    print("Listing attributes of OpenApiMessages_pb2:")
    print([x for x in dir(msg) if "Proto" in x])
    print("Listing attributes of OpenApiModelMessages_pb2:")
    print([x for x in dir(mdl) if "Proto" in x])
