import json
from pathlib import Path

from random import randrange

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer
from sc2.player import Human
from sc2.position import Point2

siege_tanks = {}

structures_being_repaired = set()

bunkers_to_build = 3
turrets_to_build = 3

workers_to_train = 22

marines_to_train = 20
marines_to_attack = 5

tanks_to_train = 5

cruisers_to_attack = 3

attack_interval = 10

class MyBot(sc2.BotAI):
    with open(Path(__file__).parent / "../botinfo.json") as f:
        NAME = json.load(f)["name"]

    def select_target(self):
        target = self.known_enemy_structures
        if target.exists:
            return target.random.position

        target = self.known_enemy_units
        if target.exists:
            return target.random.position

        if min([u.position.distance_to(self.enemy_start_locations[0]) for u in self.units]) < 10:
            return self.enemy_start_locations[0].position

        return self.state.mineral_field.random.position

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send(f"Name: {self.NAME}")

        cc = (self.units(COMMANDCENTER) | self.units(ORBITALCOMMAND))
        if not cc.exists:
            target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
            for unit in self.workers | self.units(BATTLECRUISER) | self.units(MARINE):
                await self.do(unit.attack(target))
            return
        else:
            cc = cc.first

        if iteration % attack_interval == 0:
            target = self.select_target()
            attacking = False
            attackWithAll = (iteration//attack_interval) % 10 == 0
            if self.units(MARINE).amount >= marines_to_attack:
                forces = self.units(MARINE)
                attacking = True
                if attackWithAll:
                    for unit in forces:
                        await self.do(unit.attack(target))
                else:
                    for unit in forces.idle:
                        await self.do(unit.attack(target))
            if attacking | self.units(BATTLECRUISER).amount >= cruisers_to_attack:
                forces = self.units(BATTLECRUISER)
                if attackWithAll:
                    for unit in forces:
                        await self.do(unit.attack(target))
                else:
                    for unit in forces.idle:
                        await self.do(unit.attack(target))
            if attacking:
                return

        if self.can_afford(SCV) and self.workers.amount < workers_to_train and cc.noqueue:
            await self.do(cc.train(SCV))
            return


        ## Repair broken structures
        for structure in self.units().structure.ready:
            if (structure.health < structure.health_max) and (structure.tag not in structures_being_repaired):
                scv = len(self.units(SCV)) > 0 and self.units(SCV)[0]
                if scv:
                    print("Starting to repair", structure.tag)
                    structures_being_repaired.add(structure.tag)
                    await self.do(scv(EFFECT_REPAIR, structure))
                    return
            else:
                structures_being_repaired.discard(structure.tag)

        if self.units(FUSIONCORE).exists and self.can_afford(BATTLECRUISER):
            for sp in self.units(STARPORT):
                if sp.has_add_on and sp.noqueue:
                    if not self.can_afford(BATTLECRUISER):
                        break
                    await self.do(sp.train(BATTLECRUISER))
                    return

        #### RAMP WALL:
        # Raise depos when enemies are nearby
        for depo in self.units(SUPPLYDEPOT).ready:
            for unit in self.known_enemy_units.not_structure:
                if unit.position.to2.distance_to(depo.position.to2) < 15:
                    break
            else:
                await self.do(depo(MORPH_SUPPLYDEPOT_LOWER))

        # Lower depos when no enemies are nearby
        for depo in self.units(SUPPLYDEPOTLOWERED).ready:
            for unit in self.known_enemy_units.not_structure:
                if unit.position.to2.distance_to(depo.position.to2) < 10:
                    await self.do(depo(MORPH_SUPPLYDEPOT_RAISE))
                    break

        depos = [
            Point2((max({p.x for p in d}), min({p.y for p in d})))
            for d in self.main_base_ramp.top_wall_depos
        ]

        depo_count = (self.units(SUPPLYDEPOT) | self.units(SUPPLYDEPOTLOWERED)).amount
        if self.can_afford(SUPPLYDEPOT) and not self.already_pending(SUPPLYDEPOT):
            # (x, y) positions of all existing supply depots
            depo_pos = list(map(lambda x: (int(x.position[0]), int(x.position[1])), self.units(SUPPLYDEPOT) | self.units(SUPPLYDEPOTLOWERED)))
            depos_to_build = list(filter(lambda x: x not in depo_pos, depos))
            if len(depos_to_build) > 0:
                await self.build(SUPPLYDEPOT, near=depos_to_build[0], max_distance=2, placement_step=1)
                return
            elif self.supply_left < 5:
                await self.build(SUPPLYDEPOT, near=cc.position.towards(self.game_info.map_center, 8))
                return
       #### ^^^ DEPOTS WALL

        if self.units(BARRACKS).ready.exists and self.can_afford(MARINE) and self.units(MARINE).amount < marines_to_train:
            for br in self.units(BARRACKS):
                if br.noqueue:
                    if not self.can_afford(MARINE):
                        break
                    await self.do(br.train(MARINE))
                    return

        bunkers = self.units(BUNKER)
        if depo_count >= len(depos) and self.can_afford(BUNKER) and not self.already_pending(BUNKER):
            if bunkers.amount < bunkers_to_build:
                await self.build(BUNKER, near=depos[randrange(0, len(depos))], max_distance=5)
                return

        turret_count = self.units(MISSILETURRET).amount
        if bunkers.amount >= bunkers_to_build and self.can_afford(MISSILETURRET) and not self.already_pending(MISSILETURRET):
            if turret_count < turrets_to_build:
                await self.build(MISSILETURRET, near=bunkers[randrange(0, bunkers_to_build)], max_distance=5)
                return

        if self.units(MARINE).amount > 0 and self.units(BUNKER).ready.exists and self.units(MARINE).idle.exists:
            bunkers = self.units(BUNKER).ready
            idle_marine = self.units(MARINE).idle.first
            for bunker in bunkers.idle:
                if bunker._proto.cargo_space_taken < bunker._proto.cargo_space_max:
                    await self.do(bunkers[0](LOAD_BUNKER, idle_marine))
                    return

        if self.units(SUPPLYDEPOT).exists:
            if not self.units(BARRACKS).exists:
                if self.can_afford(BARRACKS):
                    await self.build(BARRACKS, near=cc.position.towards(self.game_info.map_center, 6))
                    return

            elif self.units(BARRACKS).exists and self.units(REFINERY).amount < 2:
                if self.can_afford(REFINERY):
                    vgs = self.state.vespene_geyser.closer_than(20.0, cc)
                    for vg in vgs:
                        if self.units(REFINERY).closer_than(1.0, vg).exists:
                            break

                        worker = self.select_build_worker(vg.position)
                        if worker is None:
                            break

                        await self.do(worker.build(REFINERY, vg))
                        return

            f = self.units(ENGINEERINGBAY)
            if not f.exists:
                if self.can_afford(ENGINEERINGBAY) and self.already_pending(ENGINEERINGBAY) < 1:
                    await self.build(ENGINEERINGBAY, near=cc.position.towards(self.game_info.map_center, 8))
                    return
            f = self.units(FACTORY)
            if not f.exists:
                if self.can_afford(FACTORY) and self.already_pending(FACTORY) < 1:
                    await self.build(FACTORY, near=cc.position.random_on_distance(12))
                    return
            elif f.ready.exists:
                if self.can_afford(FACTORYTECHLAB) and not self.already_pending(FACTORYTECHLAB):
                    for factory in self.units(FACTORY).ready:
                        if factory.add_on_tag == 0:
                            print("NOW BUILDING THE FACTORYTECHLAB FOR REAL!!!!")
                            await self.do(factory.build(FACTORYTECHLAB))
                            return

            if self.units(STARPORT).amount < 2 and self.already_pending(STARPORT) < 2:
                if self.can_afford(STARPORT):
                    await self.build(STARPORT, near=cc.position.towards(self.game_info.map_center, 6).random_on_distance(9))
                    return

        for sp in self.units(STARPORT).ready:
            if sp.add_on_tag == 0:
                await self.do(sp.build(STARPORTTECHLAB))
                return

        if self.units(STARPORT).ready.exists:
            if self.can_afford(FUSIONCORE) and not self.units(FUSIONCORE).exists and self.already_pending(FUSIONCORE) < 1:
                await self.build(FUSIONCORE, near=cc.position.towards(self.game_info.map_center, 6))
                return

        if self.units(FACTORY).ready.exists:
            for factory in self.units(FACTORY).ready:
                if factory.has_add_on and self.can_afford(SIEGETANK) and factory.noqueue:
                    await self.do(factory.train(SIEGETANK))
                    break

        for s in self.units(SIEGETANK):
            siege_tank_initial_state = 'attacker' if len(siege_tanks) >= 6 else 'sieger'

            tank_status = siege_tanks.get(s.tag, siege_tank_initial_state)
            if tank_status == 'moved_to_siege':
                await self.do(s(SIEGEMODE_SIEGEMODE))
                siege_tanks[s.tag] = 'sieged'
                return
            elif tank_status == 'sieger':
                await self.do(s.move(cc.position.towards(self.game_info.map_center, 15).random_on_distance(5
)))
                siege_tanks[s.tag] = 'moving_to_siege'
                return
            elif tank_status == 'moving_to_siege':
                if s.is_idle:
                    siege_tanks[s.tag] = 'moved_to_siege'
            elif tank_status == 'attacker':
                print("Has an attacker")

        for a in self.units(REFINERY):
            if a.assigned_harvesters < a.ideal_harvesters:
                w = self.workers.closer_than(20, a)
                if w.exists:
                    await self.do(w.random.gather(a))
                    return

        for scv in self.units(SCV).idle:
            await self.do(scv.gather(self.state.mineral_field.closest_to(cc)))
            return
