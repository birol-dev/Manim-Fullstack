#!/usr/bin/env python
"""Build the bundled line icons from the ISC-licensed Lucide icon set.

Input : frontend/node_modules/lucide-react (run ``npm install`` in frontend/ first).
Output: backend/studio/assets/icons/<name>.svg, index.json (name -> search keywords) and
        LICENSE.txt (Lucide's ISC license, plus the Feather MIT notice that ships with it).

Every icon is written as a plain stroked SVG with a literal color (Manim's SVG parser does not
understand ``currentColor``)::

    <svg xmlns=... viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2" ...>

Two small adjustments make the icons behave in Manim:

* Lucide draws dots as zero-length lines (``M4 3h.01``). Manim ignores line caps, so they are
  turned into tiny circles, which the kit's stroke turns into round dots.
* An invisible anchor (two zero-length marks at the corners of the 20x20 live area) pins every
  icon's bounding box to the same square, so ``media.icon(name, size=)`` scales all icons
  consistently instead of blowing up small glyphs such as ``x`` or ``check``.

    python backend/studio/tools/build_icons.py            # rebuild everything
    python backend/studio/tools/build_icons.py --list     # show the icon names only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(STUDIO))
LUCIDE = os.path.join(REPO, "frontend", "node_modules", "lucide-react")
SRC_DIR = os.path.join(LUCIDE, "dist", "esm", "icons")
OUT_DIR = os.path.join(STUDIO, "assets", "icons")

# name -> search keywords. The first block is the set templates rely on; the rest is extra range.
# Format: "name: keyword keyword ..." (names are Lucide icon file names).
KEYWORDS = """
calendar: date schedule day event planner appointment
calendar-days: date schedule month week event planner agenda
clock: time hour watch schedule
timer: stopwatch countdown time clock duration
hourglass: time wait countdown sand deadline
map-pin: location place address venue marker where
map: location directions route area
phone: call telephone contact mobile number
mail: email envelope message contact newsletter
globe: world website web internet international language
link: url website chain connect
qr-code: scan code link barcode
tag: price label sale discount offer
percent: discount sale off offer percentage
shopping-bag: shop buy retail store purchase fashion
shopping-cart: buy cart checkout shop order
store: shop storefront retail business market boutique
gift: present birthday surprise reward holiday
star: favorite rating review feature highlight
heart: love like favorite care health
sparkles: magic new shine special ai celebrate
party-popper: celebration party confetti congratulations new year
cake: birthday dessert party bakery anniversary
trophy: winner award champion prize competition
medal: award winner place achievement sports
crown: king queen premium vip winner royal
flame: fire hot trending popular streak burn
zap: lightning fast power energy electric flash
rocket: launch startup fast growth space
coffee: cafe drink morning tea espresso break
utensils: restaurant food dining fork knife menu eat
pizza: food italian restaurant slice dinner
wine: drink glass bar restaurant evening
music: song audio note concert sound
mic: microphone podcast voice speech record
headphones: audio music podcast listen
video: film camera record movie clip
camera: photo picture photography shoot
image: picture photo gallery
film: movie cinema video reel
tv: television screen show watch
ticket: event admission entry concert pass
book: read library study novel
book-open: read study learn lesson story
graduation-cap: graduation education university school degree
pencil: edit write draw note
lightbulb: idea tip insight innovation light
brain: mind think smart learning memory
check: done yes ok correct tick success
x: close cancel no wrong remove cross
circle-check: done success approved confirmed yes
circle-x: error failed cancelled no wrong
circle-help: question help faq support
info: information about details note
triangle-alert: warning caution alert attention
bell: notification alert reminder alarm
megaphone: announcement news promote campaign broadcast
briefcase: work job business career portfolio
users: team group people community audience
user: person profile account member
user-plus: invite add member join signup
handshake: deal partnership agreement collaboration welcome
smile: happy face emoji friendly
thumbs-up: like approve good success
message-circle: chat comment talk speech
footprints: steps walk run hike trail
bike: cycling bicycle ride sport commute
dumbbell: gym fitness workout weights strength
activity: pulse heartbeat fitness health stats
heart-pulse: health heartbeat cardio wellness medical
plane: flight travel airplane trip airport
car: drive vehicle auto transport rental
train: rail railway travel transport station
house: home real estate property rent
building: office company city business apartment
mountain: hike outdoor nature summit climb
sun: sunny day weather summer bright
moon: night sleep dark evening
snowflake: winter cold snow ice
leaf: nature eco green organic plant
tree-pine: forest nature christmas camping
dog: pet puppy animal walk
cat: pet kitten animal
gamepad-2: game gaming controller play esports
trending-up: growth increase rise profit chart
trending-down: decrease drop decline loss chart
chart-column: bar chart stats analytics report
chart-pie: pie chart share stats report
dollar-sign: money price usd cost payment
euro: money price eur cost payment
wallet: money payment cash budget
piggy-bank: savings money budget bank
target: goal aim objective bullseye focus
flag: goal milestone country report finish
play: start video watch run
scissors: cut haircut salon craft barber
palette: art color paint design creative
shirt: clothing fashion apparel tshirt wear
baby: kids child infant family newborn
flower: bloom spring garden florist nature
umbrella: rain weather protection insurance
sunrise: morning dawn early start
award: prize ribbon certificate winner badge
badge-percent: discount sale offer deal
truck: delivery shipping transport logistics
package: parcel box delivery order shipping
key: access unlock password rental
lock: secure private password safe
wifi: internet network connection signal
laptop: computer work remote device
smartphone: phone mobile app device
code: programming developer software html
pen-tool: vector design illustration draw
brush: paint art design creative
guitar: music instrument band lesson
drama: theater theatre masks performance comedy
church: religion worship wedding chapel
school: education classroom learning campus
hospital: health medical clinic emergency doctor
stethoscope: doctor medical health clinic checkup
paw-print: pet animal dog cat vet
fish: seafood animal aquarium sushi
apple: fruit healthy food nutrition
salad: healthy food vegan lunch diet
ice-cream-cone: dessert sweet summer treat
beer: pub drink bar brewery
chef-hat: cooking kitchen chef restaurant catering
sofa: furniture home living room interior
bed: sleep hotel bedroom rest
bus: transport travel public commute
ship: boat cruise sea ferry
tent: camping outdoor festival
compass: direction navigate explore travel
backpack: school hiking travel bag
glasses: optical reading eyewear vision
balloon: party birthday celebration
gem: diamond jewelry premium luxury
sparkle: shine new special star
wand-sparkles: magic effect wizard transform
ribbon: awareness award gift charity
heart-handshake: charity support donate care
hand-heart: donate charity volunteer care
flower-2: bloom florist spring garden
candy: sweet treat dessert halloween
cookie: biscuit snack bakery dessert
donut: doughnut sweet bakery dessert
popcorn: cinema movie snack
cup-soda: drink soft beverage takeaway
martini: cocktail bar drink happy hour
glass-water: water drink hydration
croissant: bakery breakfast french pastry
sandwich: lunch food deli
soup: lunch food bowl
carrot: vegetable healthy farm
cherry: fruit sweet
citrus: fruit lemon orange fresh
grape: fruit wine vineyard
egg-fried: breakfast brunch food
milk: dairy drink
wheat: grain bakery farm bread
beef: meat steak butcher bbq
drumstick: chicken meat food bbq
hamburger: burger fast food
cooking-pot: kitchen cook stew recipe
notebook: notes journal diary study
library: books study archive learning
languages: translate language lesson
microscope: science lab research biology
flask-conical: science chemistry lab experiment
atom: science physics research
calculator: math accounting numbers budget
clipboard-list: checklist tasks form plan
clipboard-check: checklist done approved task
list-checks: tasks todo checklist steps
pen: write edit sign
highlighter: mark study note
ruler: measure size design
presentation: slides talk lecture board
book-marked: bookmark chapter read
bookmark: save favorite read later
newspaper: news press article blog
file-text: document page text report
test-tube: science lab test
puzzle: game solve plugin piece
dices: game chance board casino
swords: battle fight game duel
receipt: invoice bill purchase payment
credit-card: payment card checkout bank
banknote: cash money payment bill
hand-coins: pay tip donate money
scale: balance law weight justice
badge-check: verified approved quality trusted
shield-check: secure safe protected warranty
warehouse: storage inventory logistics
factory: industry manufacturing production
wrench: repair tool service fix
hammer: build tool repair construction
paintbrush: paint art decorate
paint-bucket: paint fill color decorate
drill: tool diy construction
lamp: light interior home decor
printer: print office document
scan-barcode: barcode scan product retail
barcode: product code retail
ticket-percent: coupon voucher discount deal
contact: address book person card
calendar-check: booked confirmed appointment date
calendar-clock: appointment time schedule booking
calendar-plus: add event schedule date
volleyball: beach sport ball team
goal: football soccer net score
waves: sea water swim beach surf
person-standing: person human body figure
droplet: water drop liquid hydration
mountain-snow: ski alpine winter peak
sailboat: sailing boat sea summer
wind: air breeze weather
luggage: travel suitcase trip baggage holiday
tent-tree: camping outdoor nature trip
anchor: marine harbor port ship
signpost: direction sign way
hotel: stay accommodation travel bed
castle: heritage tourism history fairy tale
landmark: museum bank monument building
tree-palm: beach tropical holiday island
sunset: evening dusk golden hour
cloud: weather sky storage
cloud-rain: rain weather wet
cloud-sun: weather partly cloudy
rainbow: colorful pride weather
bird: animal tweet nature
rabbit: animal bunny easter
turtle: animal slow sea
bug: insect nature error
shell: beach sea ocean
binoculars: explore watch nature travel
map-pinned: location saved places pinned
navigation: gps direction travel
plane-takeoff: departure flight travel
bus-front: transport city travel
car-front: drive auto rental
train-front: rail metro transport
fuel: gas station petrol car
podcast: audio show episode broadcast
radio: broadcast fm audio show
clapperboard: film movie scene director
mic-vocal: singing karaoke performance
share-2: share social network send
eye: view watch visible see
send: message share submit
at-sign: mention email handle social
hash: hashtag number tag social
message-square: chat comment feedback
thumbs-down: dislike disapprove bad
laugh: funny happy emoji fun
frown: sad unhappy emoji
users-round: team community people group
pencil-line: write edit sign
aperture: camera photography lens
gamepad: game console controller
monitor: screen desktop display
keyboard: typing computer input
mouse: pointer computer click
tablet: ipad device screen
watch: smartwatch time wearable
battery-charging: power charge energy
bluetooth: wireless connect device
cloud-upload: backup upload sync
download: save get install
upload: send publish
search: find magnify look
settings: gear options preferences
arrow-right: next forward direction
arrow-up-right: open external link grow
plus: add new more
minus: remove less subtract
chevron-right: next more forward
circle-alert: warning notice attention
circle-play: video start watch
pause: stop wait break
volume-2: sound speaker audio
bell-ring: alarm notification reminder
alarm-clock: wake morning alarm time
bot: robot ai assistant chatbot
cpu: chip processor hardware tech
circle-dot: target record radio selected
check-check: read done double confirmed
layers: stack levels design
bone: dog pet skeleton
bath: bathroom spa relax
washing-machine: laundry cleaning home
fan: cooling air summer
flashlight: torch light camping
sprout: growth plant seedling eco
recycle: sustainability eco green reuse
hand-helping: support help volunteer
hand: stop high five wave
smile-plus: add reaction emoji
tickets: events admission passes
cross: medical pharmacy health hospital
pill: medicine pharmacy health
syringe: vaccine medical injection
bandage: first aid injury care
ambulance: emergency medical rescue
dna: genetics science biology
armchair: furniture home interior
door-open: welcome open entrance
key-round: access unlock rental
hand-platter: catering serving food service
cake-slice: dessert birthday bakery
vegan: plant based healthy
shovel: dig garden construction
shield: security protection safe
""".strip()

# Everything above is built, in this order of importance for the picker.
REQUIRED = """calendar calendar-days clock timer hourglass map-pin map phone mail globe link qr-code tag percent
shopping-bag shopping-cart store gift star heart sparkles party-popper cake trophy medal crown flame zap rocket
coffee utensils pizza wine music mic headphones video camera image film tv ticket book book-open graduation-cap
pencil lightbulb brain check x circle-check circle-x circle-help info triangle-alert bell megaphone briefcase
users user user-plus handshake smile thumbs-up message-circle footprints bike dumbbell activity heart-pulse plane
car train house building mountain sun moon snowflake leaf tree-pine dog cat gamepad-2 trending-up trending-down
chart-column chart-pie dollar-sign euro wallet piggy-bank target flag play scissors palette shirt baby flower
umbrella sunrise award badge-percent truck package key lock wifi laptop smartphone code pen-tool brush guitar
drama church school hospital stethoscope paw-print fish apple salad ice-cream-cone beer chef-hat sofa bed bus
ship tent compass backpack glasses""".split()

# Optional Lucide renames: <wanted name> -> <name Lucide currently uses>, tried in order.
RENAMES = {
    "house": ["house", "home"], "triangle-alert": ["triangle-alert", "alert-triangle"],
    "circle-check": ["circle-check", "check-circle"], "circle-x": ["circle-x", "x-circle"],
    "circle-help": ["circle-help", "help-circle"], "chart-column": ["chart-column", "bar-chart-3", "chart-bar"],
    "chart-pie": ["chart-pie", "pie-chart"], "tree-pine": ["tree-pine"], "gamepad-2": ["gamepad-2"],
}

ANCHOR = (2, 22)  # corners of the 20x20 live area every icon is pinned to
HEADER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000000" '
          'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">')
DOT = re.compile(r"^M\s*(-?[\d.]+)[ ,]\s*(-?[\d.]+)\s*[hv]\.01$")


def parse_icon_node(path: str) -> list:
    """The ``__iconNode`` array of a lucide-react icon module as [(tag, {attr: value}), ...]."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    alias = re.search(r"export \{ default \} from '\./([\w-]+)\.mjs'", text)
    if alias and "const __iconNode" not in text:  # renamed icon: follow the re-export
        return parse_icon_node(os.path.join(os.path.dirname(path), alias.group(1) + ".mjs"))
    start = text.index("const __iconNode = ") + len("const __iconNode = ")
    end = text.index("];", start) + 1
    body = text[start:end]
    elements = []
    for m in re.finditer(r'\[\s*"(\w+)"\s*,\s*\{(.*?)\}\s*\]', body, re.S):
        attrs = dict(re.findall(r'([\w-]+)\s*:\s*"([^"]*)"', m.group(2)))
        attrs.pop("key", None)
        elements.append((m.group(1), attrs))
    if not elements:
        raise ValueError(f"no elements found in {path}")
    return elements


def fmt(v: str) -> str:
    return v.replace("&", "&amp;").replace('"', "&quot;")


def element_svg(tag: str, attrs: dict) -> list:
    attrs = {k: v for k, v in attrs.items() if k != "fill" or v not in ("currentColor", "none")}
    if attrs.get("fill") == "currentColor":
        attrs.pop("fill")
    if tag == "path":
        # split compound paths into sub-paths so dots (zero-length lines) become circles
        d = attrs["d"]
        pieces = [p for p in re.split(r"(?=M)", d) if p.strip()]
        if len(pieces) > 1 and any(DOT.match(p.strip()) for p in pieces):
            out, rest = [], []
            for p in pieces:
                m = DOT.match(p.strip())
                if m:
                    out.append(f'<circle cx="{m.group(1)}" cy="{m.group(2)}" r="0.4"/>')
                else:
                    rest.append(p)
            if rest:
                out.insert(0, f'<path d="{fmt("".join(rest))}"/>')
            return out
        m = DOT.match(d.strip())
        if m:
            return [f'<circle cx="{m.group(1)}" cy="{m.group(2)}" r="0.4"/>']
    body = " ".join(f'{k}="{fmt(v)}"' for k, v in attrs.items())
    return [f"<{tag} {body}/>"]


def build_svg(elements: list) -> str:
    parts = []
    for tag, attrs in elements:
        parts.extend(element_svg(tag, attrs))
    lo, hi = ANCHOR
    anchor = f'<path d="M{lo} {lo}h.001M{hi} {hi}h.001"/>'
    return HEADER + "".join(parts) + anchor + "</svg>\n"


def alias_map() -> dict:
    """Alias names (Lucide's old names) that point at the same icon file."""
    path = os.path.join(LUCIDE, "dist", "esm", "dynamicIconImports.mjs")
    aliases: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for name, target in re.findall(r'"([\w-]+)":\s*\(\)\s*=>\s*import\(\'\./icons/([\w-]+)\.mjs\'\)', fh.read()):
                if name != target:
                    aliases.setdefault(target, []).append(name)
    return aliases


def parse_keywords() -> dict:
    out = {}
    for line in KEYWORDS.splitlines():
        if ":" in line:
            name, words = line.split(":", 1)
            out[name.strip()] = words.split()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--list", action="store_true", help="print the icon names and exit")
    args = ap.parse_args()

    keywords = parse_keywords()
    names = list(dict.fromkeys(REQUIRED + list(keywords)))
    if args.list:
        print("\n".join(names))
        return
    if not os.path.isdir(SRC_DIR):
        sys.exit(f"{SRC_DIR} not found; run `npm install` in frontend/ first")

    aliases = alias_map()
    os.makedirs(args.out, exist_ok=True)
    for stale in os.listdir(args.out):
        if stale.endswith(".svg"):
            os.remove(os.path.join(args.out, stale))
    index, dropped, renamed = {}, [], {}
    for name in names:
        source = next((c for c in RENAMES.get(name, [name]) if os.path.isfile(os.path.join(SRC_DIR, c + ".mjs"))), None)
        if source is None:
            dropped.append(name)
            continue
        if source != name:
            renamed[name] = source
        elements = parse_icon_node(os.path.join(SRC_DIR, source + ".mjs"))
        with open(os.path.join(args.out, name + ".svg"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(build_svg(elements))
        words = list(keywords.get(name, []))
        words += [w for w in name.split("-") if not w.isdigit()]
        words += [w for a in aliases.get(source, []) if a != name for w in a.split("-")]
        seen = []
        for w in words:
            if w not in seen and w != name:
                seen.append(w)
        index[name] = seen
    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8", newline="\n") as fh:
        rows = [f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in sorted(index.items())]
        fh.write("{\n" + ",\n".join(" " + r for r in rows) + "\n}\n")
    shutil.copyfile(os.path.join(LUCIDE, "LICENSE"), os.path.join(args.out, "LICENSE.txt"))

    size = sum(os.path.getsize(os.path.join(args.out, f)) for f in os.listdir(args.out))
    print(f"wrote {len(index)} icons ({size / 1024:.0f} KB) to {args.out}")
    if renamed:
        print("renamed (Lucide name -> file):", renamed)
    if dropped:
        print("dropped (not in this Lucide version):", dropped)
    missing = [n for n in REQUIRED if n not in index]
    if missing:
        sys.exit(f"REQUIRED icons missing: {missing}")


if __name__ == "__main__":
    main()
