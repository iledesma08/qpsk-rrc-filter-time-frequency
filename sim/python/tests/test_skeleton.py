"""Smoke tests for the simulator package skeleton."""


def test_simulator_modules_are_importable():
    import fxp
    import gen_vectors
    import golden_freq
    import golden_time
    import rrc_coefs
    import sqnr

    assert all((fxp, gen_vectors, golden_freq, golden_time, rrc_coefs, sqnr))
