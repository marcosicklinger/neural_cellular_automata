from scipy.stats import truncexpon
import torch
import torchvision.transforms as T
import torch.nn.functional as F
from torchvision.io import write_video
from einops.layers.torch import Reduce

import numpy as np
import pylab as pl
from random import randint

from matplotlib import cm

from typing import Tuple, List


def RGBAtoFloat(images: torch.Tensor) -> torch.Tensor:
    """Converts images from 0-255 range into 0-1 range

    Args:
        images (torch.Tensor): Images in 0-255 range

    Returns:
        torch.Tensor: Images in 0-1 range
    """
    return torch.clip(images.float() / 255, 0., 1.)


def FloattoRGBA(images: torch.Tensor) -> torch.Tensor:
    """Converts images from 0-1 range into 0-255 range

    Args:
        images (torch.Tensor): Images in 0-1 range

    Returns:
        torch.Tensor: Images in 0-255 range
    """
    return torch.clip((images * 255), 0, 255).type(torch.uint8)


def RGBAtoRGB(images: torch.Tensor) -> torch.Tensor:
    """Converts a 0-1 RGBA image into RGB

    Args:
        images (torch.Tensor): RGBA images in 0-1 range

    Returns:
        torch.Tensor: RGB images in 0-1 range
    """

    if len(images.size()) < 4:
        images = torch.unsqueeze(images, 0)
    return torch.clip(images[:, :3, :, :] * images[:, 3, :, :] * 255 + (1-images[:, 3, :, :])*255, 0, 255).type(torch.uint8)


def GrayscaletoCmap(image: torch.Tensor, cmap="viridis") -> torch.Tensor:
    """Converts a 0-1 2D tensor representing an image into a colormap

    Args:
        image (torch.Tensor): 2D tensor with no channel dimension
        cmap (str, optional): color map to use, must be present in the
            matplotlib package. Defaults to "viridis".

    Returns:
        torch.Tensor: RGB image in 0-1 range
    """
    if len(image.size()) > 2:
        Exception(
            f"images must be a 1d or 2d tensor, got {image.shape} instead")
        return

    with torch.no_grad():
        scale = torch.max(image) - torch.min(image)
        if scale < 1e-6:
            image = torch.zeros_like(image)
        else:
            image = (image - torch.min(image)) / scale

    viridis = cm.get_cmap(cmap)
    return torch.tensor(viridis(image)).permute(2, 0, 1)


def center_crop(images: torch.Tensor, size: int) -> torch.Tensor:
    """Center crops a batch of images

    Args:
        images (torch.Tensor): images to center crop
        size (int): side of the square to crop

    Returns:
        torch.Tensor: Center portion of the images
    """
    return T.CenterCrop(size)(images)


def pad(images: torch.Tensor, padding: int, fill_value=0.) -> torch.Tensor:
    """Pads the images by adding "padding" pixels in both dimensions

    Args:
        images (torch.Tensor): Images to pad
        padding (int): amount of padding
        fill_value (float, optional): Value to fill the padding. Defaults to 0.

    Returns:
        torch.Tensor: Padded images
    """
    return T.Pad(padding//2, fill=fill_value)(images)


def imshow(image: torch.Tensor, fname: str = None) -> torch.Tensor:
    """Prints an image

    Args:
        image (torch.Tensor): Image to print
        fname (str): Path where to save the image.
            Defaults to None i.e. the image is not saved.
    """

    pl.imshow(np.asarray(image.cpu().permute(1, 2, 0)[:, :, :4]))
    pl.show()

    if fname is not None:
        pl.savefig(fname=fname)


def make_video(CA: "CAModel",
               n_iters: int,
               init_state: torch.Tensor = None,
               regenerating: bool = False,
               fname: str = None,
               rescaling: int = 8,
               fps: int = 10,
               initial_video: torch.Tensor = None,
               **kwargs) -> torch.Tensor:
    """Returns the video (torch.Tensor of size (n_iters, init_state.size()))
        of the evolution of the CA starting from a given initial state

    Args:
        CA (CAModel): Cellular automata to evolve and make the video
        n_iters (int): Number of iterations to evolve the CA
        init_state (torch.Tensor, optional): Initial state to evolve.
            Defaults to None, which means a seed state.
        regenerating (bool, optional): Whether to erase a square portion
            of the image during the video, useful if you want to show
            the regenerating capabilities of the CA. Defaults to False.
        fname (str, optional): File where to save the video.
            Defaults to None.
        rescaling (int, optional): Rescaling factor,
            since the CA is a small image we need to rescale it
            otherwise it will be blurry. Defaults to 8.
        fps (int, optional): Fps of the video. Defaults to 10.
        initial_video (torch.Tensor, optional): Video that gets played before
        the new one
    """

    if init_state is None:
        init_state = make_seed(1, 16, 40)

    init_state = init_state.to(CA.device)

    # set video visualization features
    video_size = init_state.size()[-1] * rescaling
    video = torch.empty((n_iters, 3, video_size, video_size), device="cpu")
    rescaler = T.Resize((video_size, video_size),
                        interpolation=T.InterpolationMode.NEAREST)

    # evolution
    with torch.no_grad():
        for i in range(n_iters):
            video[i] = RGBAtoRGB(rescaler(init_state))[0].cpu()
            init_state = CA.forward(init_state)

            if regenerating:
                if i == n_iters//3:
                    try:
                        target_size = kwargs['target_size']
                    except KeyError:
                        target_size = None
                    try:
                        constant_side = kwargs['constant_side']
                    except KeyError:
                        constant_side = None

                    init_state = make_squares(init_state,
                                              target_size=target_size,
                                              constant_side=constant_side)

    # this concatenates the new video with the old one
    if initial_video is not None:
        video = torch.cat((initial_video, video))

    if fname is not None:
        write_video(fname, video.permute(0, 2, 3, 1), fps=fps)

    return video, init_state


def make_seed(n_images: int,
              n_channels: int,
              image_size: int,
              n_CAs: int = 1,
              alpha_channel: int = -1,
              device: torch.device = "cpu") -> torch.Tensor:
    """Makes n_images seeds to start the CA, the seed is a black dot

    Args:
        n_images (int): Number of seed images to generate
        n_channels (int): Number of channels per image
        image_size (int): Side of the square image
        alpha_channel (int): channel to insert the seed. Defaults to -1

        device (torch.device, optional): Device where to save the images.
            Defaults to "cpu".

    Returns:
        torch.Tensor: Seed images
    """
    start_point = torch.zeros(
        (n_images, n_channels+n_CAs, image_size, image_size), device=device)
    start_point[:, alpha_channel, image_size//2, image_size//2] = 1.
    return start_point


def moving_average(v: np.ndarray, window_size: int) -> np.ndarray:
    """Computes moving average of a vector "v"

    Args:
        v (np.ndarray): Vector to compute the moving average
        window_size (int): Size of the window to compute the average

    Returns:
        np.ndarray: The averaged version of "v"
    """
    return np.convolve(v, np.ones(window_size), 'valid') / window_size


def side(size, constant_side=False):
    """Return size of the side to be used to erase square portion of the images"""
    if constant_side:
        return size//2
    return randint(size//6, size//2)


def make_squares(images, target_size=None, side=side, constant_side=False):
    """Sets square portion of input images to zero"""
    images = images.clone()
    if target_size is None:
        target_size = images.size()[-1]
    for i in range(images.size()[0]):
        x = randint(target_size//2-target_size//4,
                    target_size//2+target_size//4)
        y = randint(target_size//2-target_size//4,
                    target_size//2+target_size//4)
        images[i, :, x-side(target_size, constant_side)//2:x+side(target_size, constant_side) //
               2, y-side(target_size, constant_side)//2:y+side(target_size, constant_side)//2] = 0.

    return images.clone()


def make_poligon(images, target_size=None, side=side):
    """Sets random poligonal portion of input images to zero"""
    if target_size is None:
        target_size = images.size()[-1]
    for i in range(images.size()[0]):
        x1 = randint(target_size//2-target_size//4,
                     target_size//2+target_size//4)
        x2 = randint(target_size//2-target_size//4,
                     target_size//2+target_size//4)
        y1 = randint(target_size//2-target_size//4,
                     target_size//2+target_size//4)
        y2 = randint(target_size//2-target_size//4,
                     target_size//2+target_size//4)
        images[i, :, x1-side(target_size)//2:x2+side(target_size) //
               2, y1-side(target_size)//2:y2+side(target_size)//2] = 0.

    return images


def wrap_edges(images: torch.Tensor) -> torch.Tensor:
    """Pads the boundary of all images to simulate a torus

    Args:
        images (torch.Tensor): Images to pad

    Returns:
        torch.Tensor: Padded images
    """
    return F.pad(images, pad=(1, 1, 1, 1), mode='circular', value=0)


def get_living_mask(images: torch.Tensor, channels: List[int]) -> torch.Tensor:
    """Returns the a mask of the living cells in the image

    Args:
        images (torch.Tensor): images to get the living mask
        channels (List[int]): channels where to compute the living mask

    Returns:
        torch.Tensor: Living mask
    """
    if isinstance(channels, int):
        channels = [channels]
    alpha = images[:, channels, :, :]

    neighbors = F.max_pool2d(wrap_edges(alpha), 3, stride=1) > 0.1
    return torch.max(neighbors, dim=1)[0].unsqueeze(1)


def multiple_living_mask(images: torch.Tensor):
    """It gives the mask where the CA rules apply in the case where multiple alphas
    are included in the CA

    Args:
        images (torch.Tensor):
            The first index refers to the batch, the second to the alphas,
            the third and the fourth to the pixels in the image

    Returns:
        (torch.Tensor) A tensor with bool elements with the same shape on the input tensor
        that represents where each CA rule applies
    """

    # gives the biggest alpha per pixel
    biggest = Reduce('b c w h-> b 1 w h', reduction='max')(images)
    # the free cells are the ones who have all of the alphas lower than 0.1
    free = biggest < 0.1

    # this is the mask where already one of the alpha is bigger than 0.1, if more than one
    # alpha is bigger than 0.1, than the biggest one wins
    old = (images == biggest) & (images >= 0.1)
    # this is the mask of the cells neighboring each alpha
    neighbor = F.max_pool2d(wrap_edges(images), 3, stride=1) >= 0.1
    # the cells where the CA can expand are the one who are free and neighboring
    expanding = free & neighbor
    # the CA evolves int the cells where it can expand and the ones where is already present
    evolution = expanding | old

    return evolution


def n_largest_indexes(array: list, n: int = 1) -> list:
    """returns the indexes of the n largest elements of the array

    url:https://stackoverflow.com/questions/16878715/how-to-find-the-index-of-n-largest-elements-in-a-list-or-np-array-python
    """
    return sorted(range(len(array)), key=lambda x: array[x])[-n:]


class ExponentialSampler:
    def __init__(self, b: float = 2.5, min: float = 5, max: float = 40):
        """Initializes a sampler that draws values from a truncated exponential
        distribution, the higher b the more uniform will be the samples.

        Args:
            b (float, optional): Decay of the exponential. Defaults to 2.5.
            min (float, optional): Minimum value to draw. Defaults to 5.
            max (float, optional): Maximum value to draw. Defaults to 40.
        """
        self.b = b
        self.min = min
        self.max = max

    def __call__(self, size: int = 1) -> np.ndarray:
        """Draws size samples from the distribution

        Args:
            size (int, optional): Samples to draw. Defaults to 1.

        Returns:
            np.ndarray: Samples
        """
        samples = truncexpon.rvs(2.5, size=size) * \
            (self.max-self.min) / self.b + self.min
        return samples.astype(int)


def add_virus(images: torch.Tensor, original_channel: int,
              virus_channel: int, virus_rate: float = 0.1) -> torch.Tensor:
    """Adds a virus to the given images

    Args:
        images (torch.Tensor): Images to add the virus to.
        original_channel (int): Alpha channel of the original cells
        virus_channel (int): Alpha channel of the virus cells
        virus_rate (float, optional): Ratio of cells to add the virus.
            Defaults to 0.1

    Returns:
        torch.Tensor: Images with the virus added
    """
    virus_mask = torch.rand_like(images[:, original_channel]) < virus_rate

    images[:, virus_channel] = images[:, original_channel] * virus_mask.float()
    images[:, original_channel] = images[:,
                                         original_channel] * (~virus_mask).float()

    return images


class VirusGenerator:
    def __init__(self, n_channels, image_size, n_CAs, CA, virus_rate=0.1, iter_func=ExponentialSampler()):
        self.n_channels = n_channels
        self.image_size = image_size
        self.n_CAs = n_CAs
        self.CA = CA
        self.virus_rate = virus_rate
        self.iter_func = iter_func

        self.model_device = self.CA.device

    def __call__(self, n_images, device):
        start_point = make_seed(n_images, self.n_channels, self.image_size,
                                self.n_CAs, -2, self.model_device)

        batch_size = 32
        i = 0
        while i < n_images:
            start_point[i:i+batch_size] = self.CA.evolve(
                start_point[i:i+batch_size], self.iter_func()[0])
            i += batch_size

        start_point = add_virus(start_point, -2, -1, self.virus_rate)
        return start_point.to(device)


def multiple_to_single(x,n_channels,alpha_channel):
    return torch.cat((x[:,:3],
                           x[:,alpha_channel:alpha_channel+1],
                           x[:,3:n_channels]), dim=1)

def single_to_multiple(dx,shape,n_channels,alpha_channel):
    dx_new = torch.zeros(shape)
    dx_new[:,:3]=dx[:,:3]
    dx_new[:, 3:n_channels] = dx[:, 4:]
    dx_new[:, alpha_channel] = dx[:, 3]
    return dx_new
