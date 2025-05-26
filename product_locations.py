import json
import random

eans: list[str] = json.load(open("eans.json", "r"))
map: dict[str, str] = json.load(
    open("../control-room/client-app/assets/map/products.json")
)

points = map.get("features", [])
l = len(points)
print(f"Number of points: {l}")

for ean in eans:
    point_idx = random.randint(0, l - 1)
    points[point_idx]["properties"]["ean"].append(ean)

map["features"] = points
json.dump(
    map, open("../control-room/client-app/assets/map/products_fix.json", "w"), indent=2
)
