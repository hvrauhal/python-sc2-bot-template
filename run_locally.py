import json

from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer

from bot import MyBot
from random import randrange

def main():
    with open("botinfo.json") as f:
        info = json.load(f)

    race = Race[info["race"]]

    enemy_race = Race.Zerg if randrange(0,2) == 0 else Race.Protoss
    run_game(maps.get("Abyssal Reef LE"), [
        Bot(race, MyBot()),
        Computer(enemy_race, Difficulty.Medium)
    ], realtime=False, step_time_limit=2.0, game_time_limit=(60*20), save_replay_as="test.SC2Replay")

if __name__ == '__main__':
    main()
