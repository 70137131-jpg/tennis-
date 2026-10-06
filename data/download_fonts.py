from pathlib import Path
from urllib.request import urlopen

destination = Path(__file__).resolve().parents[1] / "web/public/fonts"
destination.mkdir(parents=True, exist_ok=True)
for name, location in [("DM Sans", "dmsans/DMSans%5Bopsz,wght%5D.ttf"), ("Plus Jakarta Sans", "plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf")]:
    url = "https://raw.githubusercontent.com/google/fonts/main/ofl/" + location
    with urlopen(url,timeout=60) as response:
        (destination / f"{name.replace(' ', '-')}.ttf").write_bytes(response.read())
    with urlopen("https://raw.githubusercontent.com/google/fonts/main/ofl/" + location.split('/')[0] + "/OFL.txt",timeout=60) as response:
        (destination / f"{name.replace(' ', '-')}-OFL.txt").write_bytes(response.read())
    print(f"Downloaded {name} and its SIL Open Font License")
