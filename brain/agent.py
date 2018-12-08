from .model import Actor, Critic
import numpy as np
import torch
from collections import namedtuple, deque
import random
import copy

BUFFER_SIZE = int(1e6)  # replay buffer size
BATCH_SIZE = 256         # minibatch size
GAMMA = 0.99            # discount factor
TAU = 1e-3              # for soft update of target parameters
LR = 1e-3               # learning rate
UPDATE_EVERY = 4
devc = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
torch.backends.cudnn.benchmark=True

class Agent:
    def __init__(self, state_size, action_size):
        self.action_size = action_size
        self.noise = OUNoise(action_size, 5)

        self.actor = Actor(state_size,  action_size, 5).to(devc)
        self.actor_target = Actor(state_size,  action_size, 5).to(devc)

        self.critic = Critic(state_size,  action_size, 5).to(devc)
        self.critic_target = Critic(state_size,  action_size, 5).to(devc)

        ## HARD update
        self.soft_update(self.actor, self.actor_target, 1.0)
        self.soft_update(self.critic, self.critic_target, 1.0)

        self.memory = ReplayBuffer(action_size, BUFFER_SIZE, BATCH_SIZE, 5)

        self.optimizer_actor = torch.optim.Adam(self.actor.parameters(), lr=1e-4)
        self.optimizer_critic = torch.optim.Adam(self.critic.parameters(), lr=1e-3)
        self.t_step = 0

    def act(self, state, add_noise):
        """ Act according to espilon-greedy strategy """
        state = torch.from_numpy(state).float().to(devc)
        self.actor.eval()
        with torch.no_grad():
            action_values = self.actor(state).cpu().data.numpy()
        self.actor.train()

        if add_noise:
            action_values += self.noise.sample()

        return np.clip(action_values, -1, 1)
        

    def step(self, state, action, reward, next_state, done):
        self.memory.add(state, action, reward, next_state, done)

        self.t_step += 1

        if self.t_step%UPDATE_EVERY==0:
            if len(self.memory) > BATCH_SIZE:
                experiences = self.memory.sample()
                self.learn(experiences, GAMMA)

    def learn(self, experiences, gamma):
        """Update value parameters using given batch of experience tuples.
        :param experiences: Tuple[torch.Tensor]. tuple of (s, a, r, s', done)
        :param gamma: float. discount factor
        """
        states, actions, rewards, next_states, dones = experiences

        max_Qhat = self.critic_target(next_states, self.actor_target(next_states))
        Q_target = rewards + (gamma * max_Qhat * (1 - dones))

        Q_expected = self.critic(states, actions)
        loss = torch.nn.functional.mse_loss(Q_expected, Q_target)

        self.optimizer_critic.zero_grad()
        torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 1)
        loss.backward()
        self.optimizer_critic.step()

        policy_loss = -self.critic(states, self.actor(states))
        policy_loss = policy_loss.mean()


        self.optimizer_actor.zero_grad()
        policy_loss.backward()
        self.optimizer_actor.step()

        # ------------------- update target network ------------------- #
        self.soft_update(self.actor, self.actor_target, TAU)
        self.soft_update(self.critic, self.critic_target, TAU)

        self.actor_loss = policy_loss.cpu().data.numpy()
        self.critic_loss = loss.cpu().data.numpy()


    def soft_update(self, local_model, target_model, tau):
        """Soft update model parameters.
        θ_target = τ*θ_local + (1 - τ)*θ_target
        :param local_model: PyTorch model. weights will be copied from
        :param target_model: PyTorch model. weights will be copied to
        :param tau: float. interpolation parameter
        """
        iter_params = zip(target_model.parameters(), local_model.parameters())
        for target_param, local_param in iter_params:
            tensor_aux = tau*local_param.data + (1.0-tau)*target_param.data
            target_param.data.copy_(tensor_aux)

    def reset(self):
        self.noise.reset()

class ReplayBuffer:
    """Fixed-size buffer to store experience tuples.

    Attributes:
        action_size (int): dimension of each action
        buffer_size (int): maximum size of buffer
        batch_size (int): size of each training batch
        seed (int): random seed 
    """

    def __init__(self, action_size, buffer_size, batch_size, seed):
        """Initialize a ReplayBuffer object."""
        self.action_size = action_size
        self.memory = deque(maxlen=buffer_size)
        self.batch_size = batch_size
        self.experience = namedtuple("Experience", field_names=[
                                     "state", "action", "reward", "next_state", "done"])
        self.seed = random.seed(seed)

    def add(self, state, action, reward, next_state, done):
        """Add a new experience to memory."""
        e = self.experience(state, action, reward, next_state, done)
        self.memory.append(e)

    def sample(self):
        experiences = random.sample(self.memory, k=self.batch_size)
        states = torch.from_numpy(np.vstack([e.state for e in experiences
                                             if e is not None])).float().to(devc)
        actions = torch.from_numpy(np.vstack([e.action for e in experiences
                                              if e is not None])).float().to(devc)
        rewards = torch.from_numpy(np.vstack([e.reward for e in experiences
                                              if e is not None])).float().to(devc)
        next_states = torch.from_numpy(np.vstack([e.next_state
                                                  for e in experiences
                                                  if e is not None])).float().to(devc)
        dones = torch.from_numpy(np.vstack([e.done for e in experiences
                                            if e is not None]).astype(np.uint8)).float().to(devc)

        return (states, actions, rewards, next_states, dones)

    def __len__(self):
        """Return the current size of internal memory."""
        return len(self.memory)

class OUNoise:
    """Ornstein-Uhlenbeck process."""

    def __init__(self, size, seed, mu=0.01, theta=0.15, sigma=0.1):
        """Initialize parameters and noise process."""
        self.mu = mu * np.ones(size)
        self.theta = theta
        self.sigma = sigma
        self.seed = random.seed(seed)
        self.reset()

    def reset(self):
        """Reset the internal state (= noise) to mean (mu)."""
        self.state = copy.copy(self.mu)

    def sample(self):
        """Update internal state and return it as a noise sample."""
        x = self.state
        dx = self.theta * (self.mu - x) + self.sigma * np.array([random.random() for i in range(len(x))])
        self.state = x + dx
        return self.state