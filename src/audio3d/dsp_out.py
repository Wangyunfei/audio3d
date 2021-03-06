# -*- coding: utf-8 -*-
#
# Author: Felix Pfreundtner, Matthias Lederle

import numpy as np
import scipy.io.wavfile
import pyaudio
import time
import math
import collections
import queue
import pkg_resources


class DspOut:
    """
    DspOut
    ************************
    **This class contains all otuput related variables and methods for
    the dsp algorithm.**

    It enables the overlap add algorithm and mix all binaural speaker
    output arrays to one final binaural output block. It holds the
    PortAudio methods, which are called through a Callback Thread. It also
    enables the interaction between DSP Thread and PortAudio Thread.

    Authors: Felix Pfreundtner, Matthias Lederle
    """
    def __init__(self, state_init, fft_blocksize, hopsize):
        """
        **__init__ is called by DSP and creates all variables which
        are relevant for the output part of DSP run() method's while loop.
        It setups up the format of the output block related varialbles and
        provides the playqueue and record queue.**

        Authors: Felix  Pfreundtner, Matthias Lederle
        """
        self.state = state_init
        # Number of all speakers
        self.spn = len(self.state.gui_sp)
        self.sp_binaural_block = [np.zeros((
            fft_blocksize, 2), dtype=np.float32) for sp in range(self.spn)]
        self.sp_binaural_block_out = [np.zeros((hopsize, 2), dtype=np.float32)
                                      for sp in range(self.spn)]
        self.sp_binaural_block_add = [np.zeros((fft_blocksize - hopsize, 2),
                                      dtype=np.float32) for sp in range(
            self.spn)]
        self.binaural_block = np.zeros((hopsize, 2), dtype=np.float32)
        self.continue_convolution = [True for sp in range(self.spn)]
        self.played_frames_end = 0
        self.played_block_counter = 0
        self.prior_played_block_counter = 0
        self.playbuffer = collections.deque()
        self.playback_successful = True
        self.playqueue = queue.Queue()
        self.recordqueue = queue.Queue()

    def overlap_add(self, fft_blocksize, hopsize, sp):
        """
        **Applies the overlap-add-method to the signal.**

        Adds a part of the prior generated binaural block to the beginning
        of the new generated binaural block (reason: convert fft circular
        convolution to linear convolution)

        Author: Felix Pfreundtner
        """
        # get current binaural block output of sp
        # 1. take binaural block output of current fft which don't overlap
        # with next blocks
        self.sp_binaural_block_out[sp] = self.sp_binaural_block[sp][
            0:hopsize, :]
        # 2. add relevant still remaining block output of prior ffts to
        # binaural block output of current block
        self.sp_binaural_block_out[sp] += \
            self.sp_binaural_block_add[sp][0:hopsize, :]

        # check if overlap add led to a amplitude higher than int16 max:
        sp_binaural_block_out_sp_max_amp = np.amax(np.abs(
            self.sp_binaural_block_out[sp]))
        # if yes normalize maximum output amplitude to maximum int16 range to
        #  prevent uncontrolled clipping
        if sp_binaural_block_out_sp_max_amp > 32767:
                self.sp_binaural_block_out[sp] /=  \
                    sp_binaural_block_out_sp_max_amp * 32767
        # create a new array to save remaining block output of current fft
        # and add it to the still remaining block output of prior ffts
        # 1. create new array binaural_block_add_sp_new with size (
        # fft_blocksize - hopsize)
        add_sp_arraysize = (fft_blocksize - hopsize)
        sp_binaural_block_add_sp_new = np.zeros((add_sp_arraysize, 2),
                                                dtype=np.float32)
        # 2. take still remaining block output of prior ffts and add it to
        # the zero array on front position
        sp_binaural_block_add_sp_new[0:add_sp_arraysize - hopsize, :] = \
            self.sp_binaural_block_add[sp][hopsize:, :]
        # 3. take remaining block output of current fft and add it to the
        # array on back position
        sp_binaural_block_add_sp_new[:, :] += \
            self.sp_binaural_block[sp][hopsize:, :]
        self.sp_binaural_block_add[sp] = sp_binaural_block_add_sp_new

    def mix_binaural_block(self, hopsize):
        """
        H2 -- mix_binaural_block
        ===================
        **Calculate a mixed binaural output for all speakers taking into
        account the distance of the head to each speaker.**

        Author: Felix Pfreundtner
        """
        self.binaural_block = np.zeros((hopsize, 2), dtype=np.float32)
        # maximum distance of a speaker to head in window with borderlength
        # 3.5[m] is sqrt(3.5^2+3.5^2)[m]=3.5*sqrt(2)
        # max([gui_sp[sp][1] for sp in gui_sp])
        distance_max = 3.5 * math.sqrt(2)
        for sp in range(self.spn):
            # get distance speaker to head from gui_sp
            distance_sp = self.state.gui_sp[sp]["distance"]
            # sound pressure decreases with distance 1/r
            sp_gain_factor = 1 - distance_sp / distance_max
            # add gained sp block output to a summarized block output of all
            # speakers
            self.binaural_block += self.sp_binaural_block_out[sp] * \
                sp_gain_factor / self.spn
            # if convolution for this speaker will be skipped on the
            # next iteration set binaural_block_out to zeros
            if self.continue_convolution[sp] is False:
                self.sp_binaural_block_out[sp] = np.zeros((hopsize, 2),
                                                          dtype=np.float32)
        sp_binaural_block_sp_time_max_amp = np.amax(np.abs(
            self.sp_binaural_block_out[sp][:, :]))
        if sp_binaural_block_sp_time_max_amp > 35000:
            print(sp_binaural_block_sp_time_max_amp)

    def add_to_playqueue(self):
        """
        H2 -- add_to_playqueue
        ===================
        **Sends the created binaural block of the dsp thread to the play
        thread with the playqueue.**

        Author: Felix Pfreundtner
        """
        self.playqueue.put(self.binaural_block.astype(np.int16,
                                                      copy=False).tostring())

    def add_to_recordqueue(self):
        """
        H2 -- add_to_recordqueue
        ===================
        **Adds the binaural block to the record queue.**

        Sends the created binaural block of the dsp thread to the record
        queue, which collects all created binaural blocks. Later the queue
        is read by writerecordfile().

        Author: Felix Pfreundtner
        """
        self.recordqueue.put(self.binaural_block.astype(np.int16,
                                                        copy=False))

    def callback(self, in_data, frame_count, time_info, status):
        """
        H2 -- callback
        ===================
        ** Plays the audio blocks. The function is always called by PortAudio
        when a new block is needed. The blocks are exchanged between DSP Thread
         and Play Thread through a Queue playqueue **

        Author: Felix Pfreundtner
        """
        if status:
            print("Playback Error: %i" % status)
        # played_frames_begin = self.played_frames_end
        # self.played_frames_end += frame_count
        if self.playqueue.empty() is False:
            data = self.playqueue.get()
            returnflag = pyaudio.paContinue
        else:
            data = bytes([0])
            returnflag = pyaudio.paComplete
        # print("Played Block: " + str(self.played_block_counter))
        self.played_block_counter += 1
        # print("Play: " + str(self.played_block_counter))
        return data, returnflag

    def audiooutput(self, samplerate, hopsize):
        """
        H2 -- audiooutput
        ===================
        **Starts a PortAudio Stream and handles play and pause button presses
         through the user in GUI MainWindow.**

        Author: Felix Pfreundtner
        """
        pa = pyaudio.PyAudio()
        audiostream = pa.open(format=pyaudio.paInt16,
                              channels=2,
                              rate=samplerate,
                              output=True,
                              frames_per_buffer=hopsize,
                              stream_callback=self.callback,
                              )
        # start portaudio audio stream
        audiostream.start_stream()
        # as long as stream is active (enough input) or audiostream has been
        # stopped by user
        while audiostream.is_active() or audiostream.is_stopped():
            time.sleep(0.5)
            # handle playblack pause: stop portaudio audio playback again
            if self.state.dsp_pause is True:
                audiostream.stop_stream()
            # handle playblack continue: start portaudio audio playback again
            if audiostream.is_stopped() and self.state.dsp_pause is False:
                audiostream.start_stream()
            # handle playblack stop: break while loop
            if self.state.dsp_stop is True:
                break
        # stop portaudio playback
        audiostream.stop_stream()
        audiostream.close()
        pa.terminate()

        # if stop button was not pressed
        if self.state.dsp_stop is False:
            # when not the whole input has been convolved
            if any(self.continue_convolution) is True:
                self.state.send_error("Error PC to slow - Playback Stopped")
                # set playback to unsuccessful
                self.playback_successful = False

        # finally mark audio as not paused
        self.state.dsp_pause = False
        # finally mark audio as stopped
        self.state.dsp_stop = True

    def writerecordfile(self, samplerate, hopsize):
        """
        H2 -- writerecordfile
        ===================
        **Write the whole binaural output as wave file.**

        Author: Felix Pfreundtner
        """
        binaural_record = np.zeros((self.recordqueue.qsize() * hopsize, 2),
                                   dtype=np.int16)
        position = 0
        while self.recordqueue.empty() is False:
                binaural_record[position:position+hopsize, :] = \
                    self.recordqueue.get()
                position += hopsize
        self.state.send_error(
            "Audio Recorded to File: " + pkg_resources.resource_filename(
                "audio3d", "audio_out/binauralmix.wav"))
        scipy.io.wavfile.write(pkg_resources.resource_filename("audio3d",
                               "audio_out/binauralmix.wav"), samplerate,
                               binaural_record)
