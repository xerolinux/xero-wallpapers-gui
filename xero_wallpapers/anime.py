import re

from .sources.base import Item

# Category slugs the No anime filter hides from the picker (sources use these exact slugs).
HIDDEN_CATEGORIES = frozenset({"anime", "people", "celebrities", "superhero", "superheroes"})

ANIME = (
    "anime", "animes", "manga", "manhwa", "waifu", "hentai", "chibi", "otaku", "kawaii", "isekai", "senpai",
    "genshin", "genshin impact", "honkai", "star rail", "zenless zone zero", "wuthering waves",
    "azur lane", "arknights", "blue archive", "nikke", "hatsune miku", "miku", "vocaloid",
    "naruto", "sasuke", "itachi", "kakashi", "madara", "boruto", "one piece", "luffy", "zoro",
    "dragon ball", "goku", "vegeta", "gohan", "frieza", "demon slayer", "kimetsu", "tanjiro", "nezuko",
    "jujutsu kaisen", "gojo", "sukuna", "attack on titan", "shingeki", "levi ackerman", "eren yeager",
    "evangelion", "chainsaw man", "bleach", "ichigo", "sailor moon", "my hero academia", "deku",
    "spy x family", "bocchi", "frieren", "solo leveling", "sung jin woo", "one punch man",
    "death note", "tokyo ghoul", "hunter x hunter", "fullmetal alchemist", "sword art online",
    "re zero", "konosuba", "studio ghibli", "ghibli", "totoro", "spirited away",
    "makoto shinkai", "pokemon", "pikachu", "neon genesis", "cowboy bebop", "berserk", "haikyuu",
    "tokyo revengers", "blue lock", "oshi no ko", "kaguya", "violet evergarden", "cyberpunk edgerunners",
)
PEOPLE = (
    "people", "person", "persons", "human", "humans", "portrait", "face", "faces", "selfie", "figure",
    "girl", "girls", "woman", "women", "lady", "ladies", "female", "boy", "boys", "man", "men", "male", "guy",
    "guys", "kid", "kids", "child", "children", "baby", "teen", "couple", "family", "crowd",
    "model", "models", "actress", "actor", "celebrity", "celebrities", "singer", "rapper", "dj", "idol",
    "k pop", "kpop", "musician", "dancer", "athlete", "player", "gamer", "streamer",
    "character", "characters", "cosplay", "protagonist", "hero", "heroes", "heroine", "villain",
    "superhero", "superheroes", "warrior", "warriors", "samurai", "ninja", "ronin", "soldier", "soldiers",
    "knight", "assassin", "hunter", "witch", "wizard", "sorceress", "mage", "princess", "prince", "queen",
    "king", "goddess", "angel", "elf", "vampire", "pilot", "astronaut", "cowboy", "biker", "monk", "geisha",
    "spider man", "spiderman", "batman", "superman", "iron man", "joker", "harley quinn", "deadpool",
    "wolverine", "captain america", "thor", "loki", "black widow", "wanda", "venom", "avengers", "marvel",
    "dc comics", "kratos", "geralt", "lara croft", "master chief", "aloy", "arthur morgan", "john wick",
    "ellie", "joel", "mortal kombat", "street fighter", "lady gaga", "taylor swift",
    "hair", "blonde", "brunette", "redhead", "lips", "smile", "smiling", "makeup", "uniform", "school uniform",
    "dress", "bikini", "skirt", "kimono", "hoodie", "vtuber", "youtuber", "virtual youtuber", "chan", "kun",
    "fate", "jill valentine", "leon kennedy", "resident evil", "ghost riley", "miyamoto musashi", "vagabond",
    "reze", "makima", "denji", "itadori", "okkotsu", "geto", "megumi", "nobara", "muzan", "rengoku",
    "zenitsu", "inosuke", "shinobu", "subaru natsuki", "emilia", "arona", "kaoruko",
    "character art", "touhou", "doraemon", "league of legends", "overwatch", "valorant", "apex legends",
    "final fantasy", "devil may cry", "dota", "fortnite", "tekken", "persona", "nier", "bayonetta",
    "sephiroth", "sephirot", "vergil", "malenia", "paul atreides", "hacker", "talia", "reimu", "shrine maiden",
    "cartoon", "cartoons", "shrek", "sonic", "tails", "knuckles", "mario", "luigi", "bowser", "kirby",
    "mickey", "minnie", "donald duck", "spongebob", "simpsons", "homer simpson", "scooby doo", "garfield",
    "bugs bunny", "looney tunes", "rick and morty", "family guy", "futurama", "crash bandicoot", "minions",
    "the last of us", "deadlock",
)
_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(t) for t in sorted({*ANIME, *PEOPLE}, key=len, reverse=True))
    + r")(?![a-z0-9])"
)


def blocked(item: Item) -> bool:
    text = " ".join([item.title, *item.tags]).lower().replace("-", " ").replace("_", " ")
    return bool(_PATTERN.search(text))
