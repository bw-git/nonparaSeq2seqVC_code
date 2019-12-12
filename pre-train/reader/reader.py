import torch
import torch.utils.data
import random
import numpy as np
from symbols import ph2id, sp2id, read_text
from torch.utils.data import DataLoader

class TextMelIDLoader(torch.utils.data.Dataset):
    
    def __init__(self, list_file, mean_std_file, shuffle=True):

        file_path_list = []
        with open(list_file) as f:
            lines = f.readlines()
            for line in lines:
                path, n_frame, n_text = line.strip().split()
                if int(n_frame) >= 1000:
                    continue
                file_path_list.append(path)

        random.seed(1234)
        
        if shuffle:
            random.shuffle(file_path_list)
        
        self.file_path_list = file_path_list

        self.mel_mean_std = np.float32(np.load(mean_std_file))
        self.spc_mean_std = np.float32(np.load(mean_std_file.replace('mel', 'spec')))

    def get_text_mel_id_pair(self, path):
        # Modifying this function to read your own data.
        '''
        text_input [len_text]
        text_targets [len_mel]
        mel [mel_bin, len_mel]
        speaker_id [1]
        '''

        text_path = path.replace('spec', 'text').replace('npy', 'txt').replace('log-', '')
        mel_path = path.replace('spec', 'mel')
        speaker_id = path.split('/')[-2]
        #print speaker_id

        text_input, text_targets, text_ranks = self.get_text(text_path)
        mel = np.load(mel_path)
        mel = (mel - self.mel_mean_std[0])/ self.mel_mean_std[1]

        spc = np.load(path)
        spc = (spc - self.spc_mean_std[0]) / self.spc_mean_std[1]

        if len(text_targets)< len(mel):
            #padding text:
            pad = len(mel) - len(text_targets)
            text_targets.extend(text_targets[-1:] * pad)
            text_ranks.extend(text_ranks[-1:] * pad)
        else:
            text_targets = text_targets[:len(mel)]
            text_ranks = text_ranks[:len(mel)]

        speaker_id = [sp2id[speaker_id]]
        
        text_input = torch.LongTensor(text_input)
        text_targets = torch.LongTensor(text_targets)
        mel = torch.from_numpy(np.transpose(mel))
        spc = torch.from_numpy(np.transpose(spc))
        speaker_id = torch.LongTensor(speaker_id)

        return (text_input, text_targets, mel, spc, speaker_id, text_ranks)
        
    def get_text(self,text_path):

        text = read_text(text_path)
        text_input = []
        text_targets = []
        text_ranks = []

        text_count = 0
        for start, end, ph in text:
            dur = int((end - start) / 125000. + 0.6)
            text_input.append(ph2id[ph])
            text_targets.extend([ph2id[ph]] * dur)
            text_ranks.extend([text_count]* dur)

            text_count += 1
        
        return text_input, text_targets, text_ranks

    def __getitem__(self, index):
        return self.get_text_mel_id_pair(self.file_path_list[index])

    def __len__(self):
        return len(self.file_path_list)


class TextMelIDCollate():

    def __init__(self, n_frames_per_step=2):
        self.n_frames_per_step = n_frames_per_step

    def __call__(self, batch):
        '''
        batch is list of (text_input, text_targets, mel, speaker_id)
        '''
        text_lengths = torch.IntTensor([len(x[0]) for x in batch])
        mel_lengths = torch.IntTensor([x[2].size(1) for x in batch])
        mel_bin = batch[0][2].size(0)
        spc_bin = batch[0][3].size(0)

        max_text_len = torch.max(text_lengths).item()
        max_mel_len = torch.max(mel_lengths).item()
        if max_mel_len % self.n_frames_per_step != 0:
            max_mel_len += self.n_frames_per_step - max_mel_len % self.n_frames_per_step
            assert max_mel_len % self.n_frames_per_step == 0

        text_input_padded = torch.LongTensor(len(batch), max_text_len)
        mel_padded = torch.FloatTensor(len(batch), mel_bin, max_mel_len)
        spc_padded = torch.FloatTensor(len(batch), spc_bin, max_mel_len)

        speaker_id = torch.LongTensor(len(batch))
        gate_padded = torch.FloatTensor(len(batch), max_mel_len)

        text_input_padded.zero_()
        mel_padded.zero_()
        spc_padded.zero_()
        speaker_id.zero_()
        gate_padded.zero_()

        for i in range(len(batch)):
            text =  batch[i][0]
            text_target = batch[i][1]
            mel = batch[i][2]
            spc = batch[i][3]
            text_rank = batch[i][5]

            text_input_padded[i,:text.size(0)] = text 
            mel_padded[i,  :, :mel.size(1)] = mel
            spc_padded[i,  :, :spc.size(1)] = spc
            speaker_id[i] = batch[i][4][0]
            gate_padded[i, mel.size(1)-self.n_frames_per_step:] = 1 #make sure the downsampled gate_padded have the last eng flag 1. 


        return text_input_padded, mel_padded, spc_padded, speaker_id, \
                    text_lengths, mel_lengths, gate_padded
