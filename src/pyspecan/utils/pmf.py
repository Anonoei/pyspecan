import numpy as np

class PMF:
    def __init__(self, bins=100, scale=0.2):
        self.num_bin = bins
        self.num = 0
        self._count = 0
        self._scale = scale
        self.b_range = None

        self._val = np.zeros(bins)
        self._bin = np.zeros(bins+1)

    def update(self, samples):
        mag = np.abs(samples)
        if self.b_range is None:
            self.b_range = (
                np.min(mag)*(1 + self._scale),
                np.max(mag)*(1 + self._scale)
            )
        pmf, bins = np.histogram(mag, bins=self.num_bin, range=self.b_range)

        self._val += pmf
        self.num += 1
        self._count += len(samples)

        if not np.any(bins == self._bin):
            self._bin[:] = bins

    @property
    def mean(self):
        y = self.y
        mean = 0
        for i in range(0, self.num_bin):
            mean = mean + i * y[i]
        mean = mean / self._count
        return mean

    @property
    def var(self):
        y = self.y
        mean = self.mean
        var = 0
        for i in range(0, self.num_bin):
            var = var + y[i] * (i - mean)**2
        var = var / (self._count-1)
        return var

    @property
    def std(self):
        return np.sqrt(self.var)

    @property
    def x(self):
        return self._bin[:-1]

    @property
    def y(self):
        r_pmf = self._val.real / self.num
        i_pmf = self._val.imag / self.num

        return (r_pmf/np.max(r_pmf)) + 1j*(i_pmf/np.max(i_pmf))

    @property
    def x_lim(self):
        return (self.b_range[0], self.b_range[1]) # type: ignore

    @property
    def y_lim(self):
        return (0, 1)

class ComplexPMF(PMF):
    def __init__(self, bins=100, scale=0.2):
        super().__init__(bins, scale)
        self._val = self._val.astype(np.complex64)
        self._bin = self._bin.astype(np.complex64)

    def update(self, samples):
        if self.b_range is None:
            self.b_range = (
                np.min([np.min(samples.real), np.min(samples.imag)])*(1 + self._scale),
                np.max([np.max(samples.real), np.max(samples.imag)])*(1 + self._scale)
            )
        r_pmf, r_bins = np.histogram(samples.real, bins=self.num_bin, range=self.b_range, density=False)
        i_pmf, i_bins = np.histogram(samples.imag, bins=self.num_bin, range=self.b_range, density=False)

        self._val += r_pmf.astype(np.float32) + 1j*i_pmf.astype(np.float32)
        self.num += 1
        self._count += len(samples)

        bins = r_bins + 1j*i_bins
        if not np.any(bins == self._bin):
            self._bin[:] = bins
