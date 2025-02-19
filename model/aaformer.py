"""

This file is created under the CENG 502 Project.


"""
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

import matplotlib.pyplot as plt

from model.tokens import init_agent_tokens
from model.featureextractor import FeatureExtractor
from model.representationencoder import RepresentationEncoder
from model.agentlearningdecoder import AgentLearningDecoder
from model.agentmatchingdecoder import AgentMatchingDecoder


class AAFormer(nn.Module):
    # cuda: bool 
    # num_tokens: int, number of agent tokens
    def __init__(self, cuda, c, hw, N, heads, num_tokens, im_res, reduce_dim, bypass_ot=False, sinkhorn_reg=1e-1, max_iter_ot=1000):
        super().__init__()

        self.device = "cuda" if cuda else "cpu"
        
        # Some values to store
        self.bypass_ot = bypass_ot
        self.max_iter_ot = max_iter_ot
        self.num_tokens = num_tokens 
        self.feat_res = int(math.sqrt(hw))
        self.output_res = im_res

        # Models of AAFormer 
        self.feature_extractor = FeatureExtractor(self.device, layers=50, reduce_dim=reduce_dim, c=c).to(self.device)
        self.feature_extractor.eval()    # Freeze the backbone

        self.representation_encoder = RepresentationEncoder(c, hw, N, heads).to(self.device)
        self.agent_learning_decoder = AgentLearningDecoder(cuda, c, hw, N, num_tokens, sinkhorn_reg = sinkhorn_reg).to(self.device)
        self.agent_matching_decoder = AgentMatchingDecoder(self.device, heads, c, feat_res=self.feat_res).to(self.device)

        # Last layers before prediction
        self.reshapers = [nn.ConvTranspose2d(c, c, kernel_size=2, stride=2) for i in range(int(math.log2(im_res/self.feat_res)))]
        self.reshaper = nn.Sequential(*self.reshapers)

        intermediate_dim = int(math.sqrt(c))
#        self.conv3 = nn.Conv2d(c, c//8, kernel_size=3, stride=1, padding=1, bias=False)
        self.conv3 = nn.Conv2d(c, intermediate_dim, kernel_size=3, stride=1, padding=1, bias=False)
        self.relu = nn.ReLU(inplace=True)
#        self.conv1 = nn.Conv2d(c//8, 1, kernel_size=3, stride=1, padding=1, bias=False) 
        self.conv1 = nn.Conv2d(intermediate_dim, 2, kernel_size=1, stride=1, padding=1, bias=False) 

        # Note: Output channel is not 3 (rgb), but it is 1 since we are computing a binary mask in the end.


    def forward(self, query_img, supp_imgs, supp_masks, normalize=True):

        # STEP 1: Extract Features from the backbone model (ResNet)
        # -------------------------------------------------------------------------------------------------
        
        # F_Q.shape = b, layer4.w, layer4.h, c -> 4, 16, 16, 328
        # F_S.shape = b, layer4.w, layer4.h, c
        # s_mask_list = list(b, shot, image.w, image.h) -> [4, 1, 128, 128]
        F_Q, F_S, s_mask_list = self.feature_extractor(query_img, supp_imgs, supp_masks)
        #S_mask = torch.stack(s_mask_list, dim=1)  
        S_mask_shots = torch.cat(s_mask_list, dim=1) # stack s_mask_list to a tensor -> b, shot, image.w, image.h -> 4, shot, 128, 128
        #print("F_Q.shape = ", F_Q.shape)
        #print("F_S.shape = ", F_S.shape)
        #print("S_mask_shots.shape = ", S_mask_shots.shape)

        # STEP 2.1: Pass the features from encoder 
        # -------------------------------------------------------------------------------------------------
        # F_Q_hat.shape = [b, layer4.w*layer4.h, c] -> [4, 256, 328]
        # F_S_hat.shape = [b, layer4.w*layer4.h, c]
        F_S_hat = self.representation_encoder(F_S)
        F_Q_hat = self.representation_encoder(F_Q)
#        print("F_Q_hat.shape = ", F_Q_hat.shape)
#        print("F_S_hat.shape = ", F_S_hat.shape)

        # STEP 2.2: Get Initial Agent Tokens
        # -------------------------------------------------------------------------------------------------
        # TODO: can we get rid of for loop?
        # Since every image will have different number of foreground pixels, it is not possible
        # to combine the foreground pixels of images in a single tensor. We may pad the tensors
        # since max number of foreground pixels is equal to the image area.
        X, L = [], []
        # TODO: This part assumes we are doing 1-shot learning (i.e. first for loop runs just once)
        #S_mask = torch.sum(S_mask_shots, dim=1)
        
        batch_size, shot, _, _ = S_mask_shots.shape
        F_S_h, F_S_w = F_S.shape[1], F_S.shape[2]
        
        
        #for s in range(shot):  # every mask has shape (batchsize, 1, im_res, im_res)
        M_s = torch.sum(F.interpolate(S_mask_shots, size=(F_S_h, F_S_w), mode='bilinear', align_corners=True), dim=1) 
        # M_s shape: b, layer4.h, layer4.w
        #print("M_s.shape = ", M_s.shape)         
        
        # every token has [K,c] dim for every sample in a batch        
        agent_tokens_init = init_agent_tokens(self.num_tokens, M_s, X, L, F_S) 
        
        
        # STEP 3: Pass initial agent tokens through Agent Learning Decoder and obtain agent tokens.
        # -------------------------------------------------------------------------------------------------
        # Note: agent_tokens has shape (batchsize, num_tokens, c)
        agent_tokens = self.agent_learning_decoder(agent_tokens_init, F_S_hat, M_s, bypass_ot=self.bypass_ot, max_iter_ot=self.max_iter_ot)
        
        # STEP 4: Pass agent tokens through Agent Matching Decoder
        # -------------------------------------------------------------------------------------------------
        F_q_bar = self.agent_matching_decoder(agent_tokens, F_S_hat, F_Q_hat)
      
        # STEP 5: Reshape / Conv
        # -------------------------------------------------------------------------------------------------
        # Fig.2, reshape/conv arrow before the last prediction box:
        # Assumption: Paper doesn't mention how they reshape the output of the last decoder,
        # so we assume we can use transposed convolution to upsample the output.
        
        #print(F_q_bar.shape) # ---> [batchsize, c, feat_res, feat_res]
#        output = self.reshaper(F_q_bar)
        #print(output.shape) # ---> [batchsize, c, im_res, im_res]

#####
        output = F_q_bar
#####
        output = self.conv3(output) 
        output = self.relu(output)
        output = self.conv1(output)

#####
        output = F.interpolate(output, size=(self.output_res,self.output_res), mode='bilinear', align_corners=True)
        output = torch.argmax(output, dim=1)
#####

        # Assumption: There is no specification about how to convert the predictions to segmentation masks. Yet, the predictions are not
        # in range [0,1]. We assumed that we can normalize the predictions to [0,1] range and use a threshold to binarize the prediction.
#        if normalize:
#            min = torch.amin(output, dim=(1,2,3)).unsqueeze(1).unsqueeze(1).unsqueeze(1).repeat(1,1,output.shape[-2],output.shape[-1])
#            max = torch.amax(output, dim=(1,2,3)).unsqueeze(1).unsqueeze(1).unsqueeze(1).repeat(1,1,output.shape[-2],output.shape[-1])

#            output = (output - min) / (max - min)
#            output = torch.where(output >= 0.5, 1.0, 0.0)
        return output.float()