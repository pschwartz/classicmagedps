import simpy
from classicmagedps.utils import DamageMeter


class FrostEnvironment(simpy.Environment):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mages = []
        self.PRINT = True
        self.debuffs = Debuffs(self)
        self.meter = DamageMeter(self)
        self.process(self.debuffs.run())

    def time(self):
        dt = str(round(self.now, 1))
        return '[' + str(dt) + ']'

    def p(self, msg):
        if self.PRINT:
            print(msg)

    def add_mage(self, mage):
        self.mages.append(mage)
        mage.env = self

    def add_mages(self, mages):
        self.mages.extend(mages)
        for mage in mages:
            mage.env = self

    def run(self, *args, **kwargs):
        for mage in self.mages:
            self.process(mage.rotation)
        super().run(*args, **kwargs)


class FireEnvironment(FrostEnvironment):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ignite = Ignite(self)
        self.process(self.ignite.tick())


class Debuffs:

    def __init__(self, env, coe=True):
        self.env = env
        self.scorch_stacks = 0
        self.scorch_timer = 0
        self.coe = coe
        self.wc_stacks = 0
        self.wc_timer = 0

    def scorch(self):
        self.scorch_stacks = min(self.scorch_stacks + 1, 5)
        self.scorch_timer = 30

    def wc(self):
        self.wc_stacks = min(self.wc_stacks + 1, 5)
        self.wc_timer = 30

    def run(self):
        while True:
            yield self.env.timeout(1)
            self.scorch_timer = max(self.scorch_timer - 1, 0)
            if not self.scorch_timer:
                self.scorch_stacks = 0
            self.wc_timer = max(self.wc_stacks - 1, 0)
            if not self.wc_timer:
                self.wc_stacks = 0


class Ignite:

    def __init__(self, env):
        self.env = env
        self.cum_dmg = 0
        self.ticks_left = 0
        self.owner = None
        self.stacks = 0
        self.last_crit = None
        self.counter = 0
        self._uptime = 0
        self.ticks = []

    def refresh(self, mage, dmg):
        if not self.owner:
            self.owner = mage
            self.counter += 1
        self.last_crit = self.env.now
        if self.stacks <= 4:
            self.cum_dmg += dmg
            self.stacks += 1

    def _do_dmg(self):
        tick_dmg = self.cum_dmg * 0.2

        if self.env.debuffs.coe:
            tick_dmg *= 1.1  # ignite double dips on CoE

        tick_dmg *= 1 + self.env.debuffs.scorch_stacks * 0.03  # ignite double dips on imp.scorch
        if self.owner.dmf:
            tick_dmg *= 1.1  # ignite double dips on DMF

        tick_dmg = int(tick_dmg)
        self.env.p(f"{self.env.time()} - ({self.owner.name}) ignite ({self.stacks}) tick {tick_dmg} ")
        self.env.meter.register(self.owner, tick_dmg)
        self.ticks.append(tick_dmg)

    def drop(self):
        #         if self.stacks:
        #             p(f"dropped ignite at {time(self.env)}")
        self.owner = None
        self.cum_dmg = 0
        self.stacks = 0

    def monitor(self):
        while True:
            if self.last_crit and (self.env.now - self.last_crit) > 4.15:
                self.drop()
            if self.active:
                self._uptime += 0.1
            yield self.env.timeout(0.1)

    def tick(self):
        self.env.process(self.monitor())
        while True:
            #
            if self.active:
                ignite_id = self.counter
                yield self.env.timeout(2)
                #                 print(f"old id: {ignite_id} new_id: {self.counter}")
                same_ignite = self.counter == ignite_id
                if self.active:
                    if same_ignite:
                        self._do_dmg()
                    else:
                        next_tick = (self.last_crit + 2 - self.env.now)
                        #                         p(f"next_tick: {next_tick}")
                        yield self.env.timeout(next_tick)
                        self._do_dmg()
            else:
                yield self.env.timeout(0.1)

    @property
    def active(self):
        return self.owner is not None

    @property
    def uptime(self):
        return self._uptime / self.env.now

    @property
    def avg_tick(self):
        return sum(self.ticks) / len(self.ticks)

    def report(self):
        print(f"Ignite uptime: {round(self.uptime * 100, 2)}%")
        print(f"Average tick: {round(self.avg_tick, 2)}")