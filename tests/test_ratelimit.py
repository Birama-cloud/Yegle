from app.ratelimit import RateLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limite_atteinte_puis_liberee_par_la_fenetre():
    clock = Clock()
    limiter = RateLimiter(3, 60, clock=clock)
    assert [limiter.take("ip1") for _ in range(3)] == [0, 0, 0]
    clock.now += 10
    assert limiter.take("ip1") == 50                 # le plus ancien essai sort dans 50 s
    assert limiter.take("ip2") == 0                  # chaque adresse a son propre compteur
    clock.now += 50
    assert limiter.take("ip1") == 0


def test_check_ne_compte_pas_hit_compte():
    clock = Clock()
    limiter = RateLimiter(2, 900, clock=clock)
    assert limiter.check("ip") == 0 and limiter.check("ip") == 0 and limiter.check("ip") == 0
    limiter.hit("ip")
    limiter.hit("ip")
    assert limiter.check("ip") == 900


def test_limite_zero_desactive():
    limiter = RateLimiter(0, 60)
    assert all(limiter.take("ip") == 0 for _ in range(100))


def test_cles_inactives_oubliees():
    clock = Clock()
    limiter = RateLimiter(5, 60, clock=clock)
    for i in range(999):
        limiter.hit(f"ip{i}")
    clock.now += 61
    limiter.hit("nouvelle")                          # 1000e appel : nettoyage
    assert list(limiter._hits) == ["nouvelle"]
