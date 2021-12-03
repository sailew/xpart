import logging

import numpy as np

import xobjects as xo

from .linear_normal_form import compute_linear_normal_form
from .particles import Particles

logger = logging.getLogger(__name__)

def _check_lengths(**kwargs):
    length = None
    for nn, xx in kwargs.items():
        if hasattr(xx, "__iter__"):
            if length is None:
                length = len(xx)
            else:
                if length != len(xx):
                    raise ValueError(f"invalid length len({nn})={len(xx)}")
    if 'num_particles' in kwargs.keys():
        num_particles = kwargs['num_particles']
        if num_particles is not None and length != num_particles:
            raise ValueError(
                f"num_particles={num_particles} is inconsistent with array length")
    return length

def build_particles(_context=None, _buffer=None, _offset=None, _capacity=None,
                      mode=None,
                      particle_ref=None,
                      num_particles=None,
                      x=None, px=None, y=None, py=None, zeta=None, delta=None,
                      x_norm=None, px_norm=None, y_norm=None, py_norm=None,
                      tracker=None,
                      particle_on_co=None,
                      R_matrix=None,
                      scale_with_transverse_norm_emitt=None,
                      weight=None,
                      particle_class=Particles,
                    ):

    """
    Function to create particle objects from arrays containing physical or normalized coordinates.

    Arguments:

        - mode:
            - choose between `set` (reference quantities including mass0, q0, p0c,
                gamma0, etc are taken from the reference particle.
        - particle_ref:
        - num_particles:
        - x: x coordinate of the particles
        - px: px coordinate of the particles
        - y: y coordinate of the particles
        - py: py coordinate of the particles
        - zeta: zeta coordinate of the particles
        - delta: delta coordinate of the particles
        - x_norm: transverse normalized coordinate x (in sigmas) used in combination
            with the one turn matrix R_matrix and with the transverse emittances
            provided in the argument scale_with_transverse_norm_emitt to generate
            x, px, y, py (x, px, y, py cannot be provided if x_norm, px_norm, y_norm,
            py_norm are provided).
        - px_norm: transverse normalized coordinate px (in sigmas) used in combination
            with the one turn matrix R_matrix and with the transverse emittances
            provided in the argument scale_with_transverse_norm_emitt to generate
            x, px, y, py (x, px, y, py cannot be provided if x_norm, px_norm, y_norm,
            py_norm are provided).
        - y_norm: transverse normalized coordinate y (in sigmas) used in combination
            with the one turn matrix R_matrix and with the transverse emittances
            provided in the argument scale_with_transverse_norm_emitt to generate
            x, px, y, py (x, px, y, py cannot be provided if x_norm, px_norm, y_norm,
            py_norm are provided).
        - py_norm: transverse normalized coordinate py (in sigmas) used in combination
            with the one turn matrix R_matrix and with the transverse emittances
            provided in the argument scale_with_transverse_norm_emitt to generate
            x, px, y, py (x, px, y, py cannot be provided if x_norm, px_norm, y_norm,
            py_norm are provided).
        - tracker: 
        - particle_on_co: Particle on closed orbit
        - R_matrix: 6x6 matrix defining the linearized one-turn map to be used for the transformation of
            the normalized coordinates into physical space.
        - scale_with_transverse_norm_emitt: Tuple of two elements defining the transverse normalized
            emittances used to rescale the provided transverse normalized coordinates (x, px, y, py).
        - weight: weights to be assigned to the particles.
        - _context: xobjects context in which the particle object is allocated.

    """

    assert mode in [None, 'set', 'shift', 'normalized_transverse']

    if (particle_ref is not None and particle_on_co is not None):
        raise ValueError("`particle_ref` and `particle_on_co`"
                " cannot be provided at the same time")

    if particle_ref is None:
        assert particle_on_co is not None, (
            "`particle_ref` or `particle_on_co` must be provided!")
        particle_ref = particle_on_co

    if not isinstance(particle_ref._buffer.context, xo.ContextCpu):
        particle_ref = particle_ref.copy(_context=xo.ContextCpu())

    if tracker is not None and tracker.iscollective:
        logger.warning('Ignoring collective elements in particles generation.')
        tracker = tracker._supertracker

    if zeta is None:
        zeta = 0

    if delta is None:
        delta = 0

    if (x_norm is not None or px_norm is not None
        or y_norm is not None or py_norm is not None):

        assert (x is  None and px is  None
                and y is  None and py is  None)

        if mode is None:
            mode = 'normalized_transverse'
        else:
            assert mode == 'normalized_transverse'

    if mode is None:
        mode = 'set'

    if mode == 'normalized_transverse':
        if x_norm is None: x_norm = 0
        if px_norm is None: px_norm = 0
        if y_norm is None: y_norm = 0
        if py_norm is None: py_norm = 0
    else:
        if x is None: x = 0
        if px is None: px = 0
        if y is None: y = 0
        if py is None: py = 0

    assert particle_ref._capacity == 1
    ref_dict = {
        'q0': particle_ref.q0,
        'mass0': particle_ref.mass0,
        'p0c': particle_ref.p0c[0],
        'gamma0': particle_ref.gamma0[0],
        'beta0': particle_ref.beta0[0],
    }
    part_dict = ref_dict.copy()

    if mode == 'normalized_transverse':
        if particle_on_co is None:
            assert tracker is not None
            particle_on_co = tracker.find_closed_orbit(
                particle_co_guess=Particles(
                    x=0, px=0, y=0, py=0, zeta=0, delta=0.,
                    **ref_dict))
        else:
            assert particle_on_co._capacity == 1

        if not isinstance(particle_on_co._buffer.context, xo.ContextCpu):
            particle_on_co = particle_on_co.copy(_context=xo.ContextCpu())

        if R_matrix is None:
            R_matrix = tracker.compute_one_turn_matrix_finite_differences(
                particle_on_co=particle_on_co)

        num_particles = _check_lengths(num_particles=num_particles,
            zeta=zeta, delta=delta, x_norm=x_norm, px_norm=px_norm,
            y_norm=y_norm, py_norm=py_norm)

        if scale_with_transverse_norm_emitt is not None:
            assert len(scale_with_transverse_norm_emitt) == 2

            nemitt_x = scale_with_transverse_norm_emitt[0]
            nemitt_y = scale_with_transverse_norm_emitt[1]

            gemitt_x = nemitt_x/particle_ref.beta0/particle_ref.gamma0
            gemitt_y = nemitt_y/particle_ref.beta0/particle_ref.gamma0

            x_norm_scaled = np.sqrt(gemitt_x) * x_norm
            px_norm_scaled = np.sqrt(gemitt_x) * px_norm
            y_norm_scaled = np.sqrt(gemitt_y) * y_norm
            py_norm_scaled = np.sqrt(gemitt_y) * py_norm
        else:
            x_norm_scaled = x_norm
            px_norm_scaled = px_norm
            y_norm_scaled = y_norm
            py_norm_scaled = py_norm

        WW, WWinv, Rot = compute_linear_normal_form(R_matrix)

        # Transform long. coordinates to normalized space
        XX_long = np.zeros(shape=(6, num_particles), dtype=np.float64)
        XX_long[4, :] = zeta - particle_on_co.zeta
        XX_long[5, :] = delta - particle_on_co.delta

        XX_norm_scaled = np.dot(WWinv, XX_long)

        XX_norm_scaled[0, :] = x_norm_scaled
        XX_norm_scaled[1, :] = px_norm_scaled
        XX_norm_scaled[2, :] = y_norm_scaled
        XX_norm_scaled[3, :] = py_norm_scaled

        # Transform to physical coordinates
        XX = np.dot(WW, XX_norm_scaled)

    elif mode == 'set':

        if R_matrix is not None:
            logger.warning('R_matrix provided but not used in this mode!')

        num_particles = _check_lengths(num_particles=num_particles,
            zeta=zeta, delta=delta, x=x, px=px,
            y=y, py=py)

        XX = np.zeros(shape=(6, num_particles), dtype=np.float64)
        XX[0, :] = x
        XX[1, :] = px
        XX[2, :] = y
        XX[3, :] = py
        XX[4, :] = zeta
        XX[5, :] = delta
    elif mode == "shift":

        if R_matrix is not None:
            logger.warning('R_matrix provided but not used in this mode!')

        num_particles = _check_lengths(num_particles=num_particles,
            zeta=zeta, delta=delta, x=x, px=px,
            y=y, py=py)

        XX = np.zeros(shape=(6, num_particles), dtype=np.float64)
        XX[0, :] = x + particle_ref.x
        XX[1, :] = px + particle_ref.px
        XX[2, :] = y + particle_ref.y
        XX[3, :] = py + particle_ref.py
        XX[4, :] = zeta + particle_ref.zeta
        XX[5, :] = delta + particle_ref.delta
    else:
        raise ValueError('What?!')

    part_dict['x'] = XX[0, :]
    part_dict['px'] = XX[1, :]
    part_dict['y'] = XX[2, :]
    part_dict['py'] = XX[3, :]
    part_dict['zeta'] = XX[4, :]
    part_dict['delta'] = XX[5, :]

    part_dict['weight'] = np.zeros(num_particles, dtype=np.int64)

    particles = Particles(_context=_context, _buffer=_buffer, _offset=_offset,
                          _capacity=_capacity,**part_dict)

    particles.particle_id = particles._buffer.context.nparray_to_context_array(
                                   np.arange(0, num_particles, dtype=np.int64))
    if weight is not None:
        particles.weight[:] = weight

    return particles
