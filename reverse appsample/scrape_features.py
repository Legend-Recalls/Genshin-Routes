"""
Genshin Impact AppSample Map Feature Scraper
Fetches all marker/feature data (oculi, chests, puzzles, teleport waypoints, etc.)
from the AppSample interactive map API and saves it to JSON.
"""
import json
import time
import ssl
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
API_URL = "https://game-data.lemonapi.com/gim/markers_all.v5.json?ver=d1ae6ab838569022f4acc500e8b8f98703cefe25"
BACKUP_URL = "https://game-data.b-cdn.net/gim/markers_all.v5.json?ver=d1ae6ab838569022f4acc500e8b8f98703cefe25"

ssl_ctx = ssl.create_default_context()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MARKER_NAMES = {
    "o2": "Statue of The Seven", "o3": "Teleport Waypoint",
    "o5": "Anemoculus", "o6": "Geoculus", "o8": "Mondstadt Shrine of Depths",
    "o9": "Liyue Shrine of Depths", "o15": "White Iron Chunk", "o16": "Crystal Chunk",
    "o17": "Common Chest", "o18": "Seelie", "o19": "Blazing Axe Mitachurl",
    "o20": "Wooden Shieldwall Mitachurl", "o21": "Rock Shieldwall Mitachurl",
    "o22": "Pyro Abyss Mage", "o23": "Hydro Abyss Mage", "o24": "Abyss Mage",
    "o25": "Fatui Agent", "o26": "Fatui Cicin Mage", "o27": "Ruin Guard",
    "o28": "Ruin Hunter", "o29": "Valberry", "o30": "Jueyun Chili",
    "o31": "Calla Lily", "o32": "Qingxin", "o33": "Small Lamp Grass",
    "o34": "Violetgrass", "o35": "Cecilia", "o36": "Silk Flower",
    "o37": "Dandelion Seed", "o38": "Glaze Lily", "o39": "Philanemo Mushroom",
    "o40": "Cor Lapis", "o41": "Wolfhook", "o42": "Noctilucous Jade",
    "o43": "Windwheel Aster", "o44": "Exquisite Chest", "o45": "Precious Chest",
    "o46": "Luxurious Chest", "o47": "Whopperflower", "o48": "Pyro Whopperflower",
    "o49": "Geovishap Hatchling", "o52": "World Quests",
    "o53": "Hilichurl Chieftain", "o54": "Fatui Skirmisher",
    "o55": "Hilichurl", "o56": "Hilichurl Shooter", "o57": "Samachurl",
    "o58": "Treasure Hoarder", "o59": "Slime",
    "o61": "Mist Flower Corolla", "o62": "Flaming Flower Stamen",
    "o63": "Electro Crystal", "o64": "Time Trial Challenge",
    "o65": "Windmill Mechanism", "o66": "Floating Anemo Slime",
    "o67": "Pressure Plate", "o68": "Bloatty Floatty", "o69": "Buried Chest",
    "o70": "Elemental Monument", "o71": "Torch Puzzle",
    "o72": "Large Rock Pile", "o73": "Small Rock Pile",
    "o74": "Harvestable Plant", "o75": "Sealed Chest",
    "o76": "Geogranum", "o77": "Mini Puzzle", "o78": "Starconch",
    "o79": "Enemies (First-Time Victory)", "o80": "Magical Crystal Chunk",
    "o81": "Bamboo Shoot", "o82": "Loach Pearl", "o83": "Storm Barrier",
    "o85": "Viewpoint", "o87": "Unusual Hilichurl",
    "o90": "Crystal Core", "o91": "Butterfly Wings", "o92": "Snapdragon",
    "o93": "Horsetail", "o94": "Frog",
    "o111": "Book", "o112": "Recipe", "o114": "Artifact",
    "o115": "Lizard Tail", "o116": "Crab",
    "o121": "Raw Meat", "o122": "Fish", "o123": "Fowl",
    "o124": "Matsutake", "o125": "Pinecone", "o126": "Bird Egg",
    "o127": "Mora", "o128": "Geo Sigil", "o129": "Wooden Mora Chest",
    "o130": "Cooking Ingredient",
    "o132": "Anemo Hypostasis", "o133": "Cryo Regisvine",
    "o134": "Lupus Boreas, Dominator of Wolves",
    "o135": "Electro Hypostasis", "o136": "Oceanid",
    "o137": "Pyro Regisvine", "o138": "Geo Hypostasis",
    "o139": "Starsilver", "o140": "Strange Tooth",
    "o141": "Crimson Agate", "o142": "Scarlet Quartz",
    "o144": "Pot", "o145": "Campfire/Torch", "o146": "Ruin Brazier",
    "o147": "Seelie Court", "o148": "Warming Seelie",
    "o149": "Mitachurl", "o150": "Ruin Grader",
    "o151": "The Great Snowboar King", "o152": "Frostarm Lawachurl",
    "o153": "Chilled Meat", "o154": "Domain",
    "o155": "Ancient Rime", "o156": "Eight Stone Tablets",
    "o157": "Primo Geovishap", "o158": "Frostbearing Tree",
    "o159": "Three Boxes",
    "o160": "Sweet Flower", "o161": "Mint", "o162": "Mushroom",
    "o163": "Berry", "o164": "Sunsettia", "o165": "Apple",
    "o166": "Lotus Head", "o167": "Carrot", "o168": "Radish",
    "o169": "Geovishap", "o171": "Merchant", "o172": "Iron Chunk",
    "o174": "Fir Wood", "o175": "Pine Wood", "o176": "Bamboo Segment",
    "o177": "Sandbearer Wood", "o178": "Birch Wood", "o179": "Cuihua Wood",
    "o180": "Fragrant Cedar Wood", "o181": "Cryo Hypostasis",
    "o182": "Echoing Conch", "o183": "Maguu Kenki",
    "o184": "Archaic Stone", "o185": "Sea Ganoderma",
    "o187": "Drained Conch Cup", "o188": "Foggy Forest Branch",
    "o190": "Waverider Waypoint", "o191": "Mist Bubble",
    "o192": "Glimmering Beacon", "o193": "Mural", "o194": "Electroculus",
    "o195": "Luminescent Spine", "o196": "Onikabuto", "o197": "Naku Weed",
    "o198": "Dendrobium", "o199": "Sakura Bloom", "o200": "Lavender Melon",
    "o201": "Seagrass", "o202": "Amethyst Lump",
    "o203": "Pyro Hypostasis", "o204": "Perpetual Mechanical Array",
    "o205": "Electro Seelie", "o206": "Electro Abyss Mage",
    "o207": "Thunderhelm Lawachurl", "o208": "Electrogranum",
    "o209": "Nobushi", "o210": "Fatui Mirror Maiden",
    "o211": "Crystal Marrow", "o212": "Inazuma Shrine of Depths",
    "o213": "Electro Whopperflower", "o214": "Bathysmal Vishap",
    "o215": "Ruin Sentinel", "o216": "Cube Devices",
    "o217": "Otogi Wood", "o218": "Maple Wood", "o219": "Aralia Wood",
    "o220": "Yumemiru Wood",
    "o223": "Weapon", "o224": "Ores",
    "o225": "Kid Kujirai", "o226": "Dandy",
    "o227": "Sango Pearl", "o228": "Amakumo Fruit",
    "o229": "Specter",
    "o230": "Electric Conduction", "o231": "Light-Up Tile Puzzle",
    "o233": "Medaka", "o234": "Glaze Medaka", "o235": "Sweet-Flower Medaka",
    "o236": "Aizen Medaka", "o237": "Dawncatcher", "o238": "Crystalfish",
    "o239": "Lunged Stickleback", "o240": "Betta",
    "o241": "Venomspine Fish", "o242": "Akai Maou",
    "o243": "Snowstrider", "o244": "Golden Koi", "o245": "Rusty Koi",
    "o246": "Brown Shirakodai", "o247": "Purple Shirakodai",
    "o248": "Tea-Colored Shirakodai", "o249": "Abiding Angelfish",
    "o250": "Raimei Angelfish", "o251": "Pufferfish", "o252": "Bitter Pufferfish",
    "o253": "Phase Gate", "o254": "Unagi Meat",
    "o255": "Crackling Axe Mitachurl",
    "o257": "Eye of the Storm", "o258": "Lightning Strike Probe",
    "o261": "Fishing Point", "o262": "Hydro Hypostasis",
    "o263": "Thunder Manifestation", "o264": "Bake-Danuki",
    "o265": "Wolves of the Rift", "o266": "Fluorescent Fungus",
    "o267": "Stormstone", "o268": "Mysterious Carvings",
    "o269": "Remarkable Chest", "o270": "Illusion",
    "o271": "Joyeux Voucher", "o272": "Mystmoon Chest",
    "o274": "White Pigeon", "o275": "Pale Red Crab",
    "o276": "Emerald Finch", "o277": "Cryo Crystalfly",
    "o278": "Red-Finned Unagi", "o279": "Crimson Finch",
    "o281": "Anemo Crystalfly", "o282": "Ocean Crab",
    "o283": "Black King Pigeon", "o284": "Crimson Fox",
    "o285": "Red Horned Lizard", "o288": "Golden Crab",
    "o289": "Gray Snow Cat", "o290": "Graywing Pigeon",
    "o291": "General Crab", "o292": "Golden Loach",
    "o293": "Golden Finch", "o294": "Violet Ibis",
    "o296": "Blue Horned Lizard", "o297": "Blue Frog",
    "o298": "Electro Crystalfly", "o299": "Brightcrown Pigeon",
    "o300": "Sunset Loach", "o301": "Green Horned Lizard",
    "o302": "Mud Frog", "o303": "Frog", "o304": "Sunny Loach",
    "o305": "Marrow Lizard", "o306": "Squirrel", "o307": "Sun Crab",
    "o308": "Adorned Unagi",
    "o310": "Snow Fox", "o311": "Snow Finch", "o312": "Snow Weasel",
    "o313": "Snowboar", "o315": "Geo Crystalfly",
    "o316": "Sacred Sakura", "o317": "Interaction Rewards",
    "o318": "Golden Wolflord", "o319": "The Crux: The Alcor",
    "o322": "Enkanomiya Phase Gate", "o323": "Day-Night Switching Mechanism",
    "o324": "Places of Essence Worship",
    "o329": "Gravel Mora Chest",
    "o333": "Bathysmal Vishap Herd", "o334": "Triangular Mechanism",
    "o337": "Abyss Herald",
    "o338": "Jade Chamber", "o340": "Statue of the Vassals",
    "o341": "Xenochromatic Hunter's Ray",
    "o342": "Tokoyo Legume", "o343": "Aphotium Ore",
    "o344": "The Black Serpents", "o345": "Ochimusha",
    "o347": "Energy Point", "o349": "Damaged Stone Slate",
    "o350": "Lucklight Fly", "o351": "Bluethunder Weasel",
    "o352": "Ruin Serpent", "o353": "Unique Rocks",
    "o354": "The Withering", "o355": "Starshroom",
    "o356": "Radiant Spincrystal", "o357": "Lumenspar",
    "o358": "Lumenlamp", "o360": "Orb of the Blue Depths",
    "o361": "Amber", "o362": "Imaging Conch",
    "o363": "Xenochromatic Armored Crab",
    "o364": "Xenochromatic Blubberbeast",
    "o366": "Fontaine Mora Chest",
    "o367": "Healing Spot", "o369": "Sumeru Puzzles",
    "o370": "Xenochromatic Jellyfish",
    "o383": "Echoing Conch", "o384": "Sumeru Rose",
    "o385": "Zaytun Peach", "o386": "Harra Fruit", "o387": "Viparyas",
    "o388": "Ruin Drake", "o389": "The Eremites",
    "o390": "Electro Regisvine",
    "o391": "Jadeplume Terrorshroom", "o392": "Shroomboar",
    "o393": "Dendro Crystalfly", "o394": "Dusk Bird",
    "o395": "Aranara", "o396": "Nurseries in the Wilds",
    "o397": "Stone Pillar Seal", "o398": "Phantasmal Gate",
    "o399": "Saghira Machine",
    "o400": "Nilotpala Lotus", "o401": "Kalpalata Lotus",
    "o402": "Rukkhashava Mushroom", "o403": "Dendroculus",
    "o404": "Dendrogranum", "o405": "Four-Leaf Sigil",
    "o406": "Bouncy Mushroom", "o407": "Tri-Yana Seeds",
    "o409": "Clusterleaf of Cultivation", "o410": "Cave",
    "o411": "Sumeru Shrine of Depths",
    "o412": "Adhigama Wood", "o413": "Padisarah",
    "o414": "Tree of Dreams",
    "o415": "Dendro Rock", "o416": "Dendro Pile",
    "o417": "Brightwood",
    "o418": "True Fruit Angler", "o419": "Peach of the Deep Waves",
    "o420": "Sandstorm Angler", "o421": "Sunset Cloud Angler",
    "o422": "Lazurite Axe Marlin", "o423": "Halcyon Jade Axe Marlin",
    "o424": "Aranara", "o428": "Fecund Hampers",
    "o429": "Sacred Seal",
    "o430": "Scarab", "o431": "Henna Berry",
    "o432": "Aeonblight Drake",
    "o433": "Algorithm of Semi-Intransient Matrix",
    "o434": "Primal Construct",
    "o436": "Desert Fox", "o437": "Ajilenakh Nut",
    "o439": "Sand Pile",
    "o441": "Karmaphala Wood", "o442": "Quicksand Unagi",
    "o443": "Red Tailed Lizard",
    "o444": "Primal Obelisk", "o445": "Illusion Mural",
    "o446": "Everlight Cell", "o447": "Primal Ember",
    "o448": "Primal Sandglass",
    "o449": "Mountain Date Wood", "o450": "Athel Wood",
    "o451": "Masked Weasel",
    "o452": "Dendro Hypostasis",
    "o453": "Interactive Text",
    "o454": "Consecrated Beast",
    "o455": "Iniquitous Baptist", "o456": "Hilichurl Rogue",
    "o457": "Setekh Wenut", "o458": "Chess Piece",
    "o459": "Monster From the Gray Crystals",
    "o460": "Weathered Obelisk", "o461": "Signal Spirit",
    "o462": "Sand Grease Pupa", "o463": "Mysterious Meat",
    "o464": "Cascade Pools",
    "o465": "Mysterious Stone Slate",
    "o466": "Chess Pieces Activation Device",
    "o468": "Trishiraite", "o469": "Mourning Flower",
    "o470": "Plume of Purifying Light",
    "o471": "Udumbara", "o472": "Khvarena Inscription Fragment",
    "o473": "Amrita Mayfly",
    "o474": "Gray Crystals", "o475": "Sunyata Flower",
    "o476": "Kory Drum",
    "o477": "Nirodha Fruit", "o478": "Soul Bell",
    "o479": "Fravashi Tree", "o480": "Khvarena Mayfly",
    "o481": "Farrwick", "o482": "Burgeoning Spirit",
    "o483": "Streaming Projectors", "o484": "Water Ball",
    "o485": "Brilliant Mirror", "o486": "Water Ball Easter Egg",
    "o487": "Stage", "o488": "Upper Pathway",
    "o489": "Lower Pathway", "o490": "Bidirectional Pathway",
    "o493": "Fontemer Aberrant", "o494": "Clockwork Meka",
    "o495": "Tainted Hydro Phantasm", "o496": "Breacher Primus",
    "o497": "Icewind Suite", "o498": "Emperor of Fire and Iron",
    "o499": "Pneumousia Mechanism",
    "o500": "Beryl Conch", "o501": "Romaritime Flower",
    "o502": "Lumidouce Bell", "o503": "Rainbow Rose",
    "o504": "Snow-Winged Goose", "o505": "Violetgold Angler Gull",
    "o506": "Slate Umbrellafinch",
    "o507": "Condessence Crystal", "o508": "Hydroculus",
    "o509": "Fontaine Shrine of Depths",
    "o510": "Burgundy Umbrellafinch", "o511": "Redcrown Finch",
    "o512": "Cypress Wood",
    "o513": "Hydro Crystalfly", "o514": "Darkwing Goose",
    "o515": "Flatcrest Fulmar", "o516": "Magenta Fantail Pigeon",
    "o519": "Bulle Fruit", "o520": "Aircraft",
    "o521": "Underwater Cavern", "o522": "Pluie Lotus",
    "o523": "Mallow Wood", "o524": "Ash Wood",
    "o525": "Torch Wood", "o526": "Linden Wood",
    "o527": "Streaming Axe Marlin", "o528": "Rippling Heartfeather Bass",
    "o529": "Blazing Heartfeather Bass",
    "o530": "Maintenance Mek: Initial Configuration",
    "o531": "Maintenance Mek: Water Body Cleaner",
    "o532": "Maintenance Mek: Situation Controller",
    "o533": "Maintenance Mek: Platinum Collection",
    "o534": "Viridian Fantail Pigeon", "o535": "Bluecrown Finch",
    "o536": "Chestnut Hunting Hound", "o537": "Glittergray Hunting Hound",
    "o538": "Amber Hunting Hound",
    "o539": "Experimental Field Generator",
    "o540": "Millennial Pearl Seahorse", "o541": "Fatui Operative",
    "o542": "Energy Transfer Terminal", "o543": "Stabilizer",
    "o544": "Jadewater Fruit", "o545": "Lumitoile",
    "o547": "Local Legend",
    "o548": "Lakelight Lily", "o549": "Spring of the First Dewdrop",
    "o550": "Harmonious Reed Pipe",
    "o551": "Potential Energy Orbs", "o552": "Operable Mechanism",
    "o553": "Hydro Tulpa", "o554": "Spirit Carp",
    "o555": "Treasure Map",
    "o556": "Xenochromatic Ball Octopus",
    "o557": "Sacred Ibis", "o558": "Maintenance Mek: Gold Leader",
    "o559": "Jade Incense Cauldron",
    "o560": "Ancient Ruins", "o561": "Scenes of Flowing Lotuses",
    "o562": "Carefree Simulacrum",
    "o563": "Xuanwen Beast", "o564": "Solitary Suanni",
    "o565": "Chenyu Adeptea", "o566": "Clearwater Jade",
    "o567": "Fluff-Fleece Goat", "o568": "Redbill Pelican",
    "o569": "Jade Heartfeather Bass", "o570": "Malachitin Lumibug",
    "o571": "Forest Tree Frog", "o572": "Ley Line Blossom",
    "o573": "Knocking Locations", "o574": "Key",
    "o575": "Jade Fragment", "o576": "Miasma Location",
    "o577": "Natlan Shrines of Depths", "o578": "Bookcase",
    "o579": "Resonant Anemone", "o580": "Allochromatic Anemone",
    "o581": "Autoharmonic Reed Pipes", "o582": "Swaying Eels",
    "o583": "Auric Anglerfish", "o584": "Symphony",
    "o585": "Praetorian Golem", "o586": "Legatus Golem",
    "o587": "Grimoire", "o588": "Washer Octopus",
    "o589": "Temple of Silence",
    "o590": "Gift of the Goddess of Prophecy",
    "o591": "Paper Leapfrogging", "o592": "Flying Squirrels' Aerial Adventure",
    "o593": "Move That Neck", "o594": "Play Game",
    "o595": "Magic Tonic Creation Material",
    "o596": "Natlan Mora Chest",
    "o597": "Monetoo", "o598": "Relay Ball",
    "o599": "Buried", "o600": "Warrior's Challenges",
    "o601": "Shattered Night Jade",
    "o602": "Broken, Graffiti-Marked Stone",
    "o603": "Natlan Saurians",
    "o604": "Wayob Manifestations",
    "o605": "Secret Source Automaton: Hunter-Seeker",
    "o606": "Sauroform Tribal Warriors",
    "o607": "Avatars of Lava",
    "o608": "Secret Source Automaton: Configuration Device",
    "o609": "Goldflame Qucusaur Tyrant",
    "o610": "Gluttonous Yumkasaur Mountain King",
    "o611": "Sprayfeather Gill", "o612": "Tenebrous Mimiflora",
    "o613": "Saurian Claw Succulent", "o614": "Quenepa Berry",
    "o615": "Brilliant Chrysanthemum", "o616": "Cacahuatl",
    "o617": "Grainfruit", "o619": "Candlecap Mushroom",
    "o620": "Embercore Flower", "o621": "Spinel Fruit",
    "o622": "Halberd-Crest Bird", "o623": "Crystal Beetle",
    "o624": "Pyro Crystalfly", "o625": "Phlogiston Aphid",
    "o626": "Pyroculus", "o627": "Capybara",
    "o628": "Flammabomb Wood",
    "o629": "Tenebrous Papilla",
    "o632": "Thick-Feathered Ruffed Pheasant",
    "o633": "Flowcurrent Bird", "o634": "Flowfire Bird",
    "o635": "Brown Deer", "o636": "Alpaca",
    "o637": "Long-Necked Rhino", "o638": "Flying Squirrel",
    "o639": "Tribal Secret Spaces", "o640": "Pass",
    "o641": "Courier's Trial Keystone",
    "o642": "Key With Notches", "o643": "Red Flamingo",
    "o644": "Peach Palm Wood", "o645": "Ashen Aratiku Wood",
    "o646": "White Chestnut Oak Wood",
    "o647": "Totem Challenge",
    "o648": "Pseudoshark Unihornfish",
    "o649": "Diving Rapidfighting Fish",
    "o650": "Dusk Sunfish", "o651": "Greenwave Sunfish",
    "o652": "Magma Rapidfighting Fish",
    "o653": "Phony Phlogiston Unihornfish",
    "o654": "Floral Rapidfighting Fish",
    "o655": "Withering Purpurbloom",
    "o656": "Glowing Hornshroom",
    "o657": "Cacaua Goat", "o658": "Tonatiuh",
    "o659": "Obsidian Totem Pole",
    "o660": "Wayward Hermetic Spiritspeaker",
    "o661": "Carp's Rest",
    "o662": "Throne of the Primal Fire",
    "o663": "Place of the Trial of Disembodiment",
    "o664": "Drifting Bottle",
    "o665": "Secret Source Scout Sweeper",
    "o666": "Oozing Core",
    "o667": "Secret Source Dragon Cannon",
    "o668": "Pulverite",
    "o669": "Furnace Shell Mountain Weasel",
    "o670": "Lava Dragon Statue",
    "o671": "Red Berryshroom", "o672": "Phlogiston Unit",
    "o673": "Skysplit Gembloom", "o674": "Dracolite",
    "o675": "Ancient Red-Mane Boar",
    "o676": "Ancient Glazeback Turtle",
    "o677": "Ancient Firewalker Spoonbill",
    "o678": "Ancient Scarlet-Plume Finch",
    "o680": "Geothermal Vent", "o681": "Coagulation Pearl",
    "o683": "An Audience With the Nightsoul Pillar",
    "o684": "Iridescent Inscription",
    "o685": "Canotila and the Book of Revealing",
    "o686": "Narzissenkreuz Ordo",
    "o687": "Secret Source Automaton: Overseer Device",
    "o688": "Brewblossoms", "o689": "Colossal Chromafish",
    "o690": "Capybara King", "o691": "Easybreeze Badge",
    "o692": "Paintballs", "o693": "Meeting Point",
    "o694": "Lunoculus", "o695": "Nocturnal Blossom",
    "o696": "Lakkaberry", "o697": "Midsommar Berry",
    "o698": "Icy Pebble", "o699": "Portable Bearing",
    "o700": "Frostlamp Flower",
    "o701": "Moonfall Silver", "o702": "Rainbowdrop Crystal",
    "o703": "Borderland Shrine of Depths",
    "o704": "Common Axehead Fish", "o705": "Frosted Axehead Fish",
    "o706": "Blazing Axehead Fish",
    "o707": "Veggie Mauler Shark", "o708": "Neon Mauler Shark",
    "o709": "Azuregaze Crystal-Eye", "o710": "Nightgaze Crystal-Eye",
    "o711": "Kuuvahki", "o712": "Moonlanes",
    "o713": "Assembly Modules", "o714": "Robot",
    "o715": "Tideseal Stones", "o716": "The Moon Mirror",
    "o717": "Kuuvahki Dewdrops", "o718": "Barrier Generator",
    "o719": "Sniffer Mole", "o720": "Scanning Bots",
    "o721": "Recon Bots", "o722": "Moonlit Particles",
    "o723": "Nod-Krai Mora Chest",
    "o724": "Hidden Troves", "o725": "Kuuhenki",
    "o726": "Robot Unit", "o727": "Engraving Fragment",
    "o728": "Kuuvahki Relay Mechanism",
    "o729": "ID Cards", "o730": "Stellafruit",
    "o731": "Proof of the Cognoscenti",
    "o732": "Krumkake Bolt", "o733": "Bounty Token",
    "o734": "Conch-Patterned Item",
    "o735": "Sigurd's Relic", "o736": "Radiant Beast",
    "o737": "Frostnight Scion", "o738": "Landcruiser",
    "o739": "Fatui Oprichniki", "o740": "Wasteland Wild Hunt",
    "o741": "Valiant Chronicles", "o742": "Strange Creatures",
    "o743": "Knuckle Duckle", "o744": "Radiant Moonfly",
    "o745": "Pedunculate Oak Wood", "o746": "Hazelnut Wood",
    "o747": "Silver Fir Wood", "o748": "Alder Wood",
    "o749": "Moonglow Firefly", "o750": "Atapetra Conch",
    "o751": "Rock Crab", "o752": "Puffin",
    "o753": "Dualblaze Longplume Ibis", "o754": "Dusky Goat",
    "o755": "Chestnut Goat", "o756": "Blunthorn Rhino",
    "o757": "Chic Badger", "o758": "Rimehorn Deer",
    "o759": "Frostfin Whale",
    "o760": "Oath Lantern",
    "o761": "Fortress of Meropide",
    "o762": "Frostnight Herra", "o763": "Secrets Exchanged",
    "o764": "Super-Heavy Landrover: Mechanized Fortress",
    "o765": "Pale-Furred Wolf",
    "o766": "Bunker Access Card",
    "o767": "Strange Iron Coin",
    "o768": "Fisher of Hidden Depths",
    "o769": "Lord of the Hidden Depths: Whisperer of Nightmares",
    "o770": "Winter Icelea", "o771": "Pine Amber",
    "o772": "Thornback Gecko", "o773": "Cinderneck Stork",
    "o774": "Crowned Eagle", "o775": "Mandragoras",
    "o776": "Glimmerfruit", "o777": "Spireblooms",
    "o778": "Slothsheep",
    "o779": "Intricate Blooms", "o780": "Cottonspring Flowers",
    "o781": "The Evil Eye of Blightseep",
    "o782": "Lunar Conflux Barrier",
    "o783": "The Shattered Barrier Core",
    "o784": "The Solaris Core and Nycalyx",
    "o785": "Overflowing Abyssal Power", "o786": "Prism",
    "o787": "Abyssal Fog Barriers",
    "o788": "Radiant Moongecko", "o789": "Ride in the Chariot",
    "o790": "Memory Core", "o791": "Mnemonic Cluster",
    "o792": "Noblesse Secret Treasury",
    "o793": "Secret Hall of the Realms",
    "o794": "Books of Billions",
    "o795": "Elemental Cube",
    "o796": "Segment-Domain Keeper: Organization Type",
    "o797": "Segment-Domain Keeper: Patrol Type",
    "o798": "Segment-Domain Keeper: Suppression Type",
    "o799": "Elemental Cube Display Case",
    "o800": "Path Bridging",
    "o801": "Relic Display Case",
    "o802": "Spatial Dragging",
    "o803": "Malleable Platform",
    "o804": "Building Towers on Sand",
    "o805": "Restoration Core",
    "o806": "Nation of Books",
    "o807": "World in a Painting",
    "o808": "Maranasati Casket",
    "o809": "Domain Keeper",
    "o810": "Watcher: Fallen Vigil",
    "o811": "Windrest Flower",
    "o812": "Cerulean Doppeldrake",
    "o813": "Etherwing Moth",
    "o814": "Windvigil Angler Gull",
    "o815": "Camelhorn Deer",
    "o816": "Silvermoon Hall",
    "o817": "Witch's Lodge",
}

MAP_NAMES = {
    1: "Unknown", 2: "Teyvat", 5: "Isles (1.6)", 7: "Enkanomiya",
    9: "The Chasm", 34: "Sea of Bygone Eras", 35: "Simulanka",
    36: "Ancient Sacred Mountain", 37: "Temple of Space",
    999: "Test",
}


def fetch(url, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout)
            return resp.read()
        except Exception as e:
            if attempt == retries - 1:
                print(f"  Failed to fetch {url}: {e}")
                return None
            time.sleep(1)
    return None


def scrape_features():
    print("=" * 60)
    print("  Genshin Impact AppSample Feature Scraper")
    print("=" * 60)

    print(f"\nFetching marker data from API...")
    data = fetch(API_URL)
    if data is None:
        print("  Primary API failed, trying backup...")
        data = fetch(BACKUP_URL)
    if data is None:
        print("  ERROR: Both API endpoints failed")
        return

    print(f"  Downloaded {len(data)} bytes")
    raw = json.loads(data.decode("utf-8"))

    headers = raw.get("headers", [])
    rows = raw.get("data", [])
    timestamp = raw.get("time", "")
    print(f"  Timestamp: {timestamp}")
    print(f"  Headers: {headers}")
    print(f"  Total markers: {len(rows)}")

    features = []
    type_counts = {}
    map_counts = {}

    for row in rows:
        entry = {}
        for i, key in enumerate(headers):
            if i < len(row):
                entry[key] = row[i]

        marker_id = entry.get("id", 0)
        marker_type = entry.get("type", "")
        map_id = entry.get("mid", 0)
        level = entry.get("level", 0)
        lng = entry.get("lng", 0)
        lat = entry.get("lat", 0)
        meta = entry.get("meta", None)

        name = MARKER_NAMES.get(marker_type, marker_type)
        map_name = MAP_NAMES.get(map_id, f"Map {map_id}")

        features.append({
            "id": marker_id,
            "type": marker_type,
            "name": name,
            "map_id": map_id,
            "map_name": map_name,
            "level": level,
            "lng": lng,
            "lat": lat,
            "meta": meta,
        })

        type_counts[marker_type] = type_counts.get(marker_type, 0) + 1
        map_counts[map_name] = map_counts.get(map_name, 0) + 1

    output_path = BASE_DIR / "features.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": "https://genshin-impact-map.appsample.com",
            "api_url": API_URL,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "api_timestamp": timestamp,
            "total_markers": len(features),
            "features": features,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(features)} features to {output_path}")

    summary_path = BASE_DIR / "feature_summary.json"
    summary = {
        "total_markers": len(features),
        "by_map": dict(sorted(map_counts.items(), key=lambda x: -x[1])),
        "by_type": {k: v for k, v in sorted(type_counts.items(), key=lambda x: -x[1])},
        "type_names": {k: MARKER_NAMES.get(k, k) for k in type_counts},
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  Saved summary to {summary_path}")

    print(f"\n  Breakdown by map:")
    for name, count in sorted(map_counts.items(), key=lambda x: -x[1]):
        print(f"    {name}: {count}")

    print(f"\n  Top 20 marker types:")
    for typ, count in sorted(type_counts.items(), key=lambda x: -x[1])[:20]:
        name = MARKER_NAMES.get(typ, typ)
        print(f"    {typ} ({name}): {count}")


if __name__ == "__main__":
    scrape_features()
