"""

This file is created under the CENG 502 Project.


"""
import numpy as np
import torch
from scipy.spatial.distance import cdist

# num_tokens is K in the algorithm 1 (not the K of K-shot images)
# Please refer to Algorithm 1 given in Supplementary Material
# to match the notation of variables in the comments.
# We assume X, locations of foreground pixels, is the locations of
# f_s, i..e foreground support pixel features.


# Shapes:
# X --> list[batchsize, num_foreground_pixels, 2] --> edit: since number of foreground pixels change for every image, X is a list with len(X)=batchsize
# L --> list[batchsize, num_background_pixels, 2] last dimension is (x,y) location
# f_s --> tensor(batchsize, h, w, c) 
# "h, w denote the height, width of the feature map." (Supplementary Material)
def init_agent_tokens(num_tokens, M_s, X, L, f_s):
  
    # Compute euclidean distance between every pair
    # (foreground_pixel, bacground_pixel)
    # in total, |X| x |L| pairs
    #dists_batch = torch.cdist(X, L)   # Get all the distances for K support ims
    
    # M_s shape: b, image.w, image.h
    batch_size, _, _ = M_s.shape
    for b in range(batch_size):
        # M_s.shape = b,layer4.h,layer4.w
        m = M_s[b,:,:]   # m.shape = layer4.h,layer4.w
        
        #plt.hist(m)
        #plt.show()

        # After interpolation, pixel values deteriorates from discrete 0 and 1.
        # We define 0.5 as the threshold for discriminating foregrouud from background.
        fg = np.where(m.cpu() < 0.5) # get foreground pixels
        bg = np.where(m.cpu() >= 0.5) # get background pixels

        # Create tensor with shape [num_foreground_pix, 2] where the last dimension has
        # (x,y) locations of foreground pixels
        foreground_pix = torch.stack((torch.from_numpy(fg[0]), torch.from_numpy(fg[1])), dim=1)
        background_pix = torch.stack((torch.from_numpy(bg[0]), torch.from_numpy(bg[1])), dim=1)

        #print(foreground_pix.shape)
        #print(background_pix.shape)
        #print(F_S[i,])

        X.append(foreground_pix)
        L.append(background_pix)

    #for xx,ll in zip(X,L):
    #    print(f"xx.shape = {xx.shape}   ll.shape = {ll.shape}")
    
    
     # See line 3 of Algorithm 1 in Supplementary Material:
    # for a specific location x, min distance between x and all other locations in L
    c = f_s.shape[-1]
    tokens = torch.empty(batch_size,num_tokens,c)

    for b_ind in range(batch_size):
        #print(X[b_ind].shape)
        #print(L[b_ind].shape)
        dist_mat = torch.from_numpy(cdist(X[b_ind], L[b_ind], 'euclidean')) # dist_mat 
        #print(dist_mat.shape)
        p_x = int(np.random.uniform(low=0, high=X[b_ind].shape[0], size=None))
        #print("")
        #print("p_x = ", p_x)
        
        for k in range(num_tokens):
            p_y = dist_mat[p_x].argmax()
            print()
            dist_mat[p_x, p_y] = -1 
            #print(L[b_ind])
            h, w = L[b_ind][p_y] 

            #print(f"h = {h}, w = {w}")
            
            tokens[b_ind, k] = f_s[b_ind, h, w]
            #print(tokens.shape)
            #print(tokens)

    """ 
    tokens = torch.empty((len(X), num_tokens, f_s.shape[1]))
    L_new = []
    # TODO: can we compute this jointly for all images in a batch?
    for i in range(len(X)):
        L_single = L[i]      # L for a single image in a batch

        for k in range(num_tokens):
            
            dists = torch.from_numpy(cdist(X[i], L[i], 'euclidean'))   # Get all the distances for K support ims

            # See line 3 of Algorithm 1 in Supplementary Material:
            # for a specific location x, min distance between x and all other locations in L
            d_x, d_x_ind = torch.min(dists, dim=1)  

            # We don't care about the actual distance value, so it is named as _
            # we care about which location has the furthest distance p* 
            try:
                _ , p_ind = torch.max(d_x, dim=0)
            except:
                print(">> ERROR tokens.py: d_x =", d_x.shape)

            p_furthest = X[i][p_ind, :]      # This is a location (x,y) of a pixel
            p_star = p_furthest.unsqueeze(0) # [2] --> [1,2] 
            L_single = torch.cat([L_single, p_star], dim=0) # L = (B) U (P), see line 5 in Algorithm 1

            print(f"p_furthest.data.shape = {p_furthest.data.shape}")
            f_a_k = f_s[i, :, p_furthest.data[0].long().item(), p_furthest.data[1].long().item()]
            
            tokens[i,k,:] = f_a_k
            
        L_new.append(L_single)
    """
    return tokens
    