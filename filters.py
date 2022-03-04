from scipy import signal
import numpy as np

Chebyshev_filter = signal.dlti(*signal.cheby2(8, 60, 0.7 / 10))


def decimate(x, q, n=None, ftype=Chebyshev_filter, axis=-1, zero_phase=False, zi=None):
    """
    https://github.com/scipy/scipy/blob/v1.8.0/scipy/signal/_signaltools.py#L4353-L4486

    Downsample the signal after applying an anti-aliasing filter.
    Version changed to include filter state as input to use in real time.
    Parameters
    ----------
    x : array_like
        The signal to be downsampled, as an N-dimensional array.
    q : int
        The downsampling factor. When using IIR downsampling, it is recommended
        to call `decimate` multiple times for downsampling factors higher than
        13.
    n : int, optional
        The order of the filter (1 less than the length for 'fir'). Defaults to
        8 for 'iir' and 20 times the downsampling factor for 'fir'.
    ftype : ``dlti`` instance, optional
        `dlti` object, uses that object to filter before downsampling.
    axis : int, optional
        The axis along which to decimate.
    zero_phase : bool, optional
        Prevent phase shift by filtering with `filtfilt` instead of `lfilter`
        when using an IIR filter, and shifting the outputs back by the filter's
        group delay when using an FIR filter. The default value of ``True`` is
        recommended, since a phase shift is generally not desired.
        .. versionadded:: 0.18.0
    zi : array_like, optional
        Internal filter state to be used instead of zero inertia.
    Returns
    -------
    y : ndarray
        The down-sampled signal.
    zi : array_like
        Filter state after filtering.
    See Also
    --------
    resample : Resample up or down using the FFT method.
    resample_poly : Resample using polyphase filtering and an FIR filter.
    Notes
    -----
    The ``zero_phase`` keyword was added in 0.18.0.
    The possibility to use instances of ``dlti`` as ``ftype`` was added in
    0.18.0.
    """

    import operator

    x = np.asarray(x)
    q = operator.index(q)

    if n is not None:
        n = operator.index(n)

    if isinstance(ftype, signal.dlti):
        system = ftype._as_tf()  # Avoids copying if already in TF form
        b, a = system.num, system.den
    else:
        raise ValueError('invalid ftype')

    result_type = x.dtype
    if result_type.kind in 'bui':
        result_type = np.float64
    b = np.asarray(b, dtype=result_type)
    a = np.asarray(a, dtype=result_type)

    sl = [slice(None)] * x.ndim
    a = np.asarray(a)

    if a.size == 1:  # FIR case
        b = b / a
        if zero_phase:
            y = signal.resample_poly(x, 1, q, axis=axis, window=b)
        else:
            # upfirdn is generally faster than lfilter by a factor equal to the
            # downsampling factor, since it only calculates the needed outputs
            n_out = x.shape[axis] // q + bool(x.shape[axis] % q)
            y = signal.upfirdn(b, x, up=1, down=q, axis=axis)
            sl[axis] = slice(None, n_out, None)

    else:  # IIR case
        if zero_phase:
            y = signal.filtfilt(b, a, x, axis=axis)
        else:
            if zi is None:
                zi = signal.lfilter_zi(b, a)
                zi = zi * x[0]
            y, zi = signal.lfilter(b, a, x, axis=axis, zi=zi)
        sl[axis] = slice(None, None, q)

    return y[tuple(sl)], zi
