import torch
from torch import nn
from typing import Tuple, List

from .utils import *


def n_largest_indexes(array: list, n: int = 1) -> list:
    """returns the indexes of the n largest elements of the array
    url:https://stackoverflow.com/questions/16878715/how-to-find-the-index-of-n-largest-elements-in-a-list-or-np-array-python
    """
    if n==0: return None
    return sorted(range(len(array)), key=lambda x: array[x])[-n:]


class NCALoss:
    """Custom loss function for the neural CA, computes the
        distance of the target image vs the predicted image and adds a
        penalization term
    """

    def __init__(self, target: torch.Tensor, criterion=torch.nn.MSELoss,
                alpha_channels: Tuple[int] = [3]):
        """Initializes the loss function by storing the target image and setting
            the criterion
        Args:
            target (torch.Tensor): Target image
            criterion (Loss function, optional): 
                Loss criteria, used to compute the distance between two images.
                Defaults to torch.nn.MSELoss.
            l (float): Regularization factor, useful to penalize the perturbation
        """
        self.target = target.detach().clone()
        self.criterion = criterion(reduction="none")
        self.alpha_channels = alpha_channels

    def __call__(self, x: torch.Tensor, *args, **kwargs) -> Tuple[torch.Tensor]:
        """Returns the loss and the index of the image with maximum loss
        Args:
            x (torch.Tensor): Images to compute the loss
        Returns:
            Tuple(torch.Tensor, torch.Tensor): 
                Average loss of all images in the batch, 
                index of the image with maximum loss
        """

        alpha = torch.sum(x[:, self.alpha_channels], dim=1).unsqueeze(1)
        predicted = torch.cat((x[:, :3], alpha), dim=1)

        losses = self.criterion(predicted, self.target).mean(dim=[1, 2, 3])

        return losses
 


class CellRatioLoss:
    """Custom loss function for the multiple CA, computes the
        distance of the target image vs the predicted image, adds a
        penalization term and penalizes the number of original cells
    """
    def __init__(self,alpha_channels: Tuple[int] = [3]):
        """Args:
            The same as the NCALoss and 
            alpha (optiona, float): multiplicative constant to regulate the importance of the original cell ratio
        """

        self.alpha_channels = alpha_channels

    def __call__(self, x:torch.Tensor, *args, **kwargs)->Tuple[torch.Tensor]:
        original_cells = x[:, self.alpha_channels[0]].sum(dim=[1, 2])
        virus_cells = x[:, self.alpha_channels[1]].sum(dim=[1, 2])
        original_cell_ratio = original_cells / (original_cells+virus_cells+1e-8)
        
        return original_cell_ratio



class NCADistance():
    def model_distance(self, model1: nn.Module, model2: nn.Module):
        """Computes the distance between the parameters of two models"""
        p1, p2 = ruler.parameters_to_vector(model1), ruler.parameters_to_vector(model2)
        return nn.MSELoss()(p1, p2)

    def __init__(self, model1: nn.Module, model2: nn.Module, l: float = 0.):
        """Extension of the NCALoss that penalizes the distance between two
        models using the parameter l
        """
        self.model1 = model1
        self.model2 = model2
        self.l = l


    def __call__(self, x: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """Returns the loss and the index of the image with maximum loss
        Args:
            x (torch.Tensor): Images to compute the loss
        Returns:
            Tuple(torch.Tensor, torch.Tensor): 
                Average loss of all images in the batch, 
                index of the image with maximum loss
        """

        return self.l * self.model_distance(self.model1, self.model2)


class CombinedLoss:
    """Combines several losses into one loss function that depends on the number of steps
    """
    def __init__(self, losses:List[nn.Module], combination_function, log_step=60):
        """Args:
            Losses (List[nn.Module]): List of losses to combine
            combination_function (Callable): Function to combine the losses, it takes as input the
                number of steps and the epoch, and it outputs a vector of floats as long as the number of losses
        """
        self.losses=losses
        self.f=combination_function
        self.log_step=log_step

        

    def __call__(self, x, n_steps=0, n_epoch=0, evolutions_per_image=0, *args, **kwargs) -> torch.Tensor:
        losses = torch.stack([loss(x) for loss in self.losses]).float()
        return torch.matmul(self.f(n_steps,n_epoch,evolutions_per_image),losses) #This gives problem if some variables are not in cuda

    def log_loss(self,x:torch.Tensor)->float:
        return self.losses[0](x)

