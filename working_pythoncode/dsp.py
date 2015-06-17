# -*- coding: utf-8 -*-
"""
Created on Fri May 22 16:27:57 2015

@author: Felix Pfreundtner
"""

import numpy as np
import dsp_in
import dsp
import dsp_out
import gui_utils
import threading
import matplotlib.pyplot as plt
import multiprocessing
import gui_utils

from dsp_signal_handler import DspSignalHandler

import time

class Dsp:
    def __init__(self, gui_dict_init, gui_stop_init, gui_pause_init):
        self.gui_dict = gui_dict_init
        self.prior_head_angle_dict = dict.fromkeys(gui_dict_init, [])
        self.error_list = dict.fromkeys(gui_dict_init, [])
        self.outputsignal_sample_number = dict.fromkeys(gui_dict_init, [])
        # Set number of bufferblocks between fft block convolution and audio block playback
        self.number_of_bufferblocks = 10
        # Create Input Object which contains mono input samples of sources and hrtf impulse responses samples
        self.DspIn_Object = dsp_in.DspIn(gui_dict_init)
        # Create Output Object which contains binaural output samples
        self.DspOut_Object = dsp_out.DspOut(gui_dict_init, self.DspIn_Object.fft_blocksize, self.DspIn_Object.sp_blocksize, gui_stop_init, gui_pause_init)
        # Variable counts number of already convolved blocks, initialized with zero
        self.blockcounter = 0

        # Here a signal handler will be created
        # Usage:
        # When error occurs, call the function self.signal_handler.send_error()
        # The only parameter (A String!) is the message you want to send
        self.signal_handler = DspSignalHandler()

        # @author Matthias Lederle
        # self.blocknumpy = self.DspIn_Object.get_one_block_of_samples(
        #     self.DspIn_Object.gui_dict_init[sp][2],
        #     self.DspIn_Object.block_begin_end,
        #     self.DspIn_Object.sp_param[4],
        #     self.DspIn_Object.sp_param[sp][2],
        #     self.DspIn_Object.sp_param[sp][3],
        #     self.DspIn_Object.sp_param[5],
        #     self.DspIn_Object.sp_param[6]
        # )

    def run(self):
        # run the main while loop as long as there a still samples to be read in from speaker wave files
        while any(self.DspOut_Object.continue_convolution_dict.values()) is True:

            # actualize variables with gui
            self.gui_dict = gui_utils.gui_dict
            self.DspOut_Object.gui_stop = gui_utils.gui_stop
            self.DspOut_Object.gui_pause = gui_utils.gui_pause

            # print the number of already done FFT / Block iterations
            print("FFT Block " + str(self.blockcounter) + ":")
            # set the begin and end of the speaker wave block which needs to be read in this iteration
            #if self.blockcounter==0:
            self.DspIn_Object.set_block_begin_end()

            # iterate over all active speakers sp
            for sp in self.gui_dict:
                # fill binaural block output array of speaker sp with zeros
                self.DspOut_Object.binaural_block_dict[sp] = np.zeros((self.DspIn_Object.fft_blocksize, 2), dtype=np.int16)

                # if speaker wave file still has unread samples start convolution, else skip convolution
                if self.DspOut_Object.continue_convolution_dict[sp] is True:
                    # check whether head position to speaker sp has changed
                    if self.gui_dict[sp][0] != self.prior_head_angle_dict[sp]:
                        # if head position has changed load new fitting hrtf file as numpy array
                        self.DspIn_Object.get_hrtfs(self.gui_dict[sp], sp)
                        # save head position to speaker of this block in prior_head_angle dict
                        self.prior_head_angle_dict[sp] = self.gui_dict[sp][0]

                    # Load wave block of speaker sp with speaker_blocksize (fft_blocksize-hrtf_blocksize+1) and current block begin_end
                    self.DspIn_Object.sp_block_dict[sp], self.DspOut_Object.continue_convolution_dict[sp] = self.DspIn_Object.get_block(
                        self.gui_dict[sp][2], self.DspIn_Object.block_begin_end[
                                                      0], self.DspIn_Object.block_begin_end[
                                                      1], self.DspIn_Object.sp_param[sp], \
                                                          self.DspIn_Object.sp_blocksize)

                    # normalize sp block if requested
                    self.DspIn_Object.normalize(self.gui_dict[sp][3], sp)

                    # apply window to sp input in sp_block_dict
                    #self.DspIn_Object.sp_block_dict[sp]= self.DspIn_Object.apply_window(self.DspIn_Object.sp_block_dict[sp], self.DspIn_Object.hann)

                    # for the left and the right ear channel
                    for l_r in range(2):
                        # convolve hrtf with speaker block input
                        self.DspOut_Object.fft_convolve(self.DspIn_Object.sp_block_dict[sp],self.DspIn_Object.hrtf_block_dict[sp][:, l_r],self.DspIn_Object.fft_blocksize,self.DspIn_Object.sp_max_gain_dict[sp],self.DspIn_Object.hrtf_max_gain_dict[sp][l_r], self.DspIn_Object.wave_param_common[0], self.DspIn_Object.hrtf_database, self.DspIn_Object.kemar_inverse_filter, self.DspIn_Object.hrtf_blocksize, self.DspIn_Object.sp_blocksize, sp, l_r)

                        # apply window to sp binaural block output left or right ear in binaural_block_dict
                        #self.DspIn_Object.hann = self.DspIn_Object.build_hann_window(self.DspIn_Object.fft_blocksize)
                        #self.DspOut_Object.binaural_block_dict[sp][0:,l_r]= self.DspIn_Object.apply_window(self.DspOut_Object.binaural_block_dict[sp][0:,l_r], self.DspIn_Object.hann)


                # model speaker position change about 1° per block (0.02s) in clockwise rotation
                #self.gui_dict[sp][0]+=30
                #if self.gui_dict[sp][0] >= 360:
                    #self.gui_dict[sp][0] -= 360

                # overlap samples [0: fft_block_size-sp_block_size] sp block with prior sp block samples [sp_block_size: fft_block_size] and save in binaural_block_dict_out
                # save end of block [sp_block_size: fft_block_size] in binaural_block_dict_add to overlap in the next iteration
                self.DspOut_Object.binaural_block_dict_out[sp], self.DspOut_Object.binaural_block_dict_add[sp] = self.DspOut_Object.overlap_add(self.DspOut_Object.binaural_block_dict[sp], self.DspOut_Object.binaural_block_dict_out[sp], self.DspOut_Object.binaural_block_dict_add[sp], self.DspIn_Object.fft_blocksize, self.DspIn_Object.sp_blocksize)

            # Mix binaural stereo blockoutput of every speaker to one binaural stereo block having regard to speaker distances
            self.DspOut_Object.binaural_block = self.DspOut_Object.mix_binaural_block(self.DspOut_Object.binaural_block_dict_out, self.DspIn_Object.sp_blocksize, self.gui_dict)


            # Add mixed binaural stereo blocks to a time continuing binaural output
            self.DspOut_Object.lock.acquire()
            try:
                self.DspOut_Object.binaural = self.DspOut_Object.add_to_binaural(self.DspOut_Object.binaural, self.DspOut_Object.binaural_block, self.blockcounter)
            finally:
                self.DspOut_Object.lock.release()

            #self.DspOut_Object.binaural = self.DspOut_Object.overlapp_add_window(self.DspOut_Object.binaural_block_dict[sp][0:,1], self.blockcounter, self.DspIn_Object.fft_blocksize, self.DspOut_Object.binaural)


            # Begin Audio Playback if specified Number of Bufferblocks has been convolved
            if self.blockcounter == self.number_of_bufferblocks:
                startaudiooutput = threading.Thread(target=self.DspOut_Object.audiooutput, args = (2, self.DspIn_Object.wave_param_common[0], self.DspIn_Object.sp_blocksize))
                startaudiooutput.start()
                # startaudiooutput.join()

            # wait until audioplayback finished with current block
            while self.blockcounter-self.DspOut_Object.play_counter > self.number_of_bufferblocks and not all(self.DspOut_Object.continue_convolution_dict.values()) is False:
                 time.sleep(1/self.DspIn_Object.wave_param_common[0]*100)


            # increment number of already convolved blocks
            self.blockcounter += 1

            # handle playback pause
            while self.DspOut_Object.gui_pause is True:
                time.sleep(0.1)
                self.DspOut_Object.gui_pause = gui_utils.gui_pause
            # handle playback stop
            if self.DspOut_Object.gui_stop is True:
                break
        # show plot of the output signal binaural_dict_scaled
        # plt.plot(self.DspOut_Object.binaural)
        # plt.show()
        # Write generated output signal binaural_dict_scaled to file
        self.DspOut_Object.writebinauraloutput(self.DspOut_Object.binaural, self.DspIn_Object.wave_param_common, self.gui_dict)

