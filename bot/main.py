import json
from pathlib import Path

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer
from sc2.player import Human
from sc2.position import Point2

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

        if min([u.position.distance_to(self.enemy_start_locations[0]) for u in self.units]) < 5:
            return self.enemy_start_locations[0].position

        return self.state.mineral_field.random.position

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send(f"Name: {self.NAME}")

        cc = (self.units(COMMANDCENTER) | self.units(ORBITALCOMMAND))
        if not cc.exists:
            target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
            for unit in self.workers | self.units(BATTLECRUISER):
                await self.do(unit.attack(target))
            return
        else:
            cc = cc.first


        if iteration % 50 == 0 and self.units(BATTLECRUISER).amount > 2:
            target = self.select_target()
            forces = self.units(BATTLECRUISER)
            if (iteration//50) % 10 == 0:
                for unit in forces:
                    await self.do(unit.attack(target))
            else:
                for unit in forces.idle:
                    await self.do(unit.attack(target))

        if self.can_afford(SCV) and self.workers.amount < 22 and cc.noqueue:
            await self.do(cc.train(SCV))

        if self.units(FUSIONCORE).exists and self.can_afford(BATTLECRUISER):
            for sp in self.units(STARPORT):
                if sp.has_add_on and sp.noqueue:
                    if not self.can_afford(BATTLECRUISER):
                        break
                    await self.do(sp.train(BATTLECRUISER))


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
            if depo_count >= len(depos):
                return
            depo = list(depos)[depo_count]
            r = await self.build(SUPPLYDEPOT, near=depo, max_distance=2, placement_step=1)
        elif self.supply_left < 3 and not self.already_pending(SUPPLYDEPOT):
            if self.can_afford(SUPPLYDEPOT):
                await self.build(SUPPLYDEPOT, near=cc.position.towards(self.game_info.map_center, 8))
        #### ^^^ DEPOTS WALL

        if self.units(SUPPLYDEPOT).exists:
            if not self.units(BARRACKS).exists:
                if self.can_afford(BARRACKS):
                    await self.build(BARRACKS, near=cc.position.towards(self.game_info.map_center, 8))

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
                        break

            if self.units(BARRACKS).ready.exists:
                f = self.units(FACTORY)
                if not f.exists:
                    if self.can_afford(FACTORY):
                        await self.build(FACTORY, near=cc.position.towards(self.game_info.map_center, 8))
                elif f.ready.exists and self.units(STARPORT).amount < 2:
                    if self.can_afford(STARPORT):
                        await self.build(STARPORT, near=cc.position.towards(self.game_info.map_center, 30).random_on_distance(8))

        for sp in self.units(STARPORT).ready:
            if sp.add_on_tag == 0:
                await self.do(sp.build(STARPORTTECHLAB))

        if self.units(STARPORT).ready.exists:
            if self.can_afford(FUSIONCORE) and not self.units(FUSIONCORE).exists:
                await self.build(FUSIONCORE, near=cc.position.towards(self.game_info.map_center, 8))

        for a in self.units(REFINERY):
            if a.assigned_harvesters < a.ideal_harvesters:
                w = self.workers.closer_than(20, a)
                if w.exists:
                    await self.do(w.random.gather(a))

        for scv in self.units(SCV).idle:
            await self.do(scv.gather(self.state.mineral_field.closest_to(cc)))
