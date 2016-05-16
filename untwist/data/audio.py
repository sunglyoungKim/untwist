"""
Audio representations, i.e. Wave, Spectrum, Spectrogram.
Should always inherit from ndarray, but utility functions may be added, e.g. loading audio files, playing or plotting

"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.io import wavfile
from ..base import types
from ..base.exceptions import *
from ..soundcard import audio_driver
from matplotlib.colors import LinearSegmentedColormap



""" utility functions"""

def ensure2D(ndarray):    
    if len(ndarray.shape)==1:
        ndarray = ndarray.reshape((ndarray.shape[0],1))    
    return ndarray

eps = np.spacing(1)


"""
Time domain signal. Layout is one column per channel
"""

class Signal(np.ndarray):
    
    __array_priority__ = 10
    def __new__(cls, data, sample_rate= 44100):
        data = ensure2D(data)
        instance = np.ndarray.__new__(cls, 
            data.shape, dtype = data.dtype, strides = data.strides, buffer = data)
        instance.sample_rate = sample_rate
        return instance

    def __array_finalize__(self, obj):
        if obj is None: return
        self.sample_rate = getattr(obj, 'sample_rate', None)

    def __array_prepare__(self, out_arr, context = None):        
        return np.ndarray.__array_prepare__(self, out_arr, context)
        
    def __array_wrap__(self, out_arr, context = None):        
        return np.ndarray.__array_wrap__(self, out_arr, context)
                
    @property  
    def num_channels(self):
        return 1 if len(self.shape)==1 else self.shape[1]

    @property
    def num_frames(self):
        return self.shape[0]

    def check_mono(self):
        if self.num_channels > 1:
            raise ChannelLayoutException()
            
    def as_ndarray(self):
        return np.array(self)

class Wave(Signal):
    
    def __init__(self, samples, sample_rate):
        self.stream = None
        super(Wave, self).__init__(samples, sample_rate)

    def __array_finalize__(self, obj):
        if obj is None: return
        self.stream = getattr(obj, 'stream', None)
        self.sample_rate = getattr(obj, 'sample_rate', None)
            
    @classmethod
    def read(cls,filename):
        sample_rate, samples = wavfile.read(filename)
        if samples.dtype==np.dtype('int16'):            
            samples = samples.astype(types.float_) / np.iinfo(np.dtype('int16')).min
        if len(samples.shape)==1:
            samples = samples.reshape((samples.shape[0],1))
        instance = cls(samples, sample_rate)
        return instance
        
    def write(self, filename):
        wavfile.write(filename, self.sample_rate, self)
        
    @classmethod
    def mix(cls, waves):
        if len(waves)==1: return waves[0].normalize()
        lengths = [np.atleast_2d(w).shape[0] for w in waves]
        widths = [np.atleast_2d(w).shape[1] for w in waves]
        if len(set(lengths)) > 1 or len(set(widths)) > 1:
            raise ArgumentException("inputs should have the same shape")
        mixed = np.zeros(waves[0].shape)
        for w in waves:
            w.normalize()
            w = np.divide(w,len(waves)) 
            mixed = mixed + w
        instance = cls(mixed, waves[0].sample_rate)
        return instance

    def normalize(self):
        return Wave(np.divide(self, np.max(self,0)), self.sample_rate)                
            
    def zero_pad(self, start_frames, end_frames=0):
        start = np.zeros((start_frames, self.num_channels),types.float_)
        end = np.zeros((end_frames,self.num_channels),types.float_)
        # avoid shape to be (N,)        
        tmp = self.reshape(self.shape[0], self.num_channels)
        return Wave(np.concatenate((start,tmp,end)), self.sample_rate)

    def plot(self):
        time_values = np.arange(self.num_frames)/float(self.sample_rate)
        if self.num_channels == 1:
            f = plt.plot(time_values, self)
        else:
            f, axes = plt.subplots(self.num_channels, sharex=True)
            for ch in range(self.num_channels):        
                axes[ch].plot(time_values, self[:,ch])
        plt.xlabel('time (s)')
        return f

    def play(self, stop_func = None):
        if self.stream is None: 
            self.stream = audio_driver.play(
                self, sr = self.sample_rate, stop_func = stop_func
            )

    def stop(self):
        audio_driver.stop(self.stream)
        self.stream = None
        
    @classmethod 
    def record(cls, max_seconds = 10, num_channels = 2, sr = 44100,
        stop_func= None):
        return audio_driver.record(max_seconds, num_channels, sr, stop_func)


"""
Audio Spectrum. Initialize with a complex spectral frame and sample rate. 
"""

class Spectrum(Signal):
        
    def __array_finalize__(self, obj):
        if obj is None: return        
        self.sample_rate = getattr(obj, 'sample_rate', None)
        self.sample_rate = getattr(obj, 'window_size', None)
        self.sample_rate = getattr(obj, 'hop_size', None)
    
    def magnitude(self):
       return np.abs(self) 

    def phase(self):
        return np.angle(self)
        
    def plot(self):# magnitude and phase
        f, axes = plt.subplots(2, sharex=True)
        axes[0].plot(self.magnitude())
        axes[0].plot(self.phase())
        return f
       
        
"""
Audio Spectrogram (complex). 
Rows are frequency bins (0th is the lowest frequency), columns are time bins.
"""
        
class Spectrogram(Spectrum):
    
    def __new__(cls, data, sample_rate = 44100, window_size = 1024, hop_size = 512):
        instance = Signal.__new__(cls, data, sample_rate)             
        instance.window_size = window_size
        instance.hop_size = hop_size
        return instance
    
    def __array_finalize__(self, obj):
        if obj is None: return        
        self.sample_rate = getattr(obj, 'sample_rate', None)
        self.window_size = getattr(obj, 'window_size', None)
        self.hop_size = getattr(obj, 'hop_size', None)
   
    @property  
    def num_channels(self):
        return 1

    @property
    def num_frames(self):
        return self.shape[1]
            
    def plot(self,**kwargs):
        return self.magnitude_plot(**kwargs )
        
    def magnitude_plot(self, colormap = "CMRmap", min_freq = 0, max_freq = None, 
        axes = None, label_x = True, label_y = True, title = None, 
        colorbar = True, log_mag = True):            
        mag = self.magnitude()
        if log_mag: 
            mag = 20. * np.log10((mag / np.max(mag)) + np.spacing(1))
            min_val = -60
        else:
            min_val = 0
        if max_freq is None: max_freq = self.sample_rate / 2.0
        hop_secs = float(self.hop_size) / self.sample_rate
        time_values = np.arange(self.num_frames) * hop_secs
        bin_hz = self.sample_rate / (self.shape[0] * 2)
        freq_values = np.arange(self.shape[0]) * bin_hz
        if axes == None: axes = plt.gca()
        img = axes.imshow(mag, 
            cmap = colormap,  
            aspect="auto", 
            vmin = min_val,
            origin ="low",
            extent = [0, time_values[-1], min_freq, max_freq]
        )
        if colorbar:plt.colorbar(img, ax = axes)
        if label_x: axes.set_xlabel("time (s)")
        if label_y: axes.set_ylabel("freq (hz)")        
        plt.setp(axes.get_xticklabels(), visible = label_x)
        plt.setp(axes.get_yticklabels(), visible = label_y)
        if title is not None:
            axes.text(0.9, 0.9, title, horizontalalignment = 'right',
                bbox={'facecolor':'white', 'alpha':0.7, 'pad':5}, 
                transform=axes.transAxes)
        return axes

class TFMask(Spectrogram):
    
    def plot(self, mask_color = (1, 0, 0, 0.5), min_freq = 0, max_freq = None, 
        axes = None, label_x = True, label_y = True, title = None):
        if axes == None: 
            colormap =  LinearSegmentedColormap.from_list("map",["white","black"])
        else:
            alpha_color = [mask_color[0], mask_color[1], mask_color[2], 0]
            colormap = LinearSegmentedColormap.from_list("map", [alpha_color, mask_color])
        Spectrogram.magnitude_plot(
            self, colormap, min_freq, max_freq, axes, label_x, label_y, title, 
            False, False
            )
        
class BinaryMask(TFMask):
    def __new__(cls, target, background, threshold = 0):
        tm = target.magnitude() + eps
        bm = background.magnitude() + eps
        mask = (20 * np.log10(tm / bm) > threshold).astype(types.float_)
        instance = TFMask.__new__(cls, mask)
        instance.sample_rate = target.sample_rate
        instance.window_size = target.window_size
        instance.hop_size = target.hop_size
        return instance
    
class RatioMask(TFMask):
    def __new__(cls, target, background, p = 1):
        tm = target.magnitude() + eps
        bm = background.magnitude() + eps
        mask = (tm**p / (tm + bm)**p).astype(types.float_)
        instance = TFMask.__new__(cls, mask)
        instance.sample_rate = target.sample_rate
        instance.window_size = target.window_size
        instance.hop_size = target.hop_size
        return instance        