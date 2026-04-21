import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from scipy.stats import norm

# Step 1: Generate random Gaussian data
np.random.seed(42)
true_mean = 5.0
true_std = 2.0
n_samples = 1000

data = np.random.normal(loc=true_mean, scale=true_std, size=n_samples)

# Step 2: Create histogram of data
hist_counts, bin_edges, _ = plt.hist(data, bins=30, density=True, alpha=0.6, color='blue', edgecolor='black', label='Histogram')

# Step 3: Define Gaussian fit function
def gaussian(x, mu, sigma):
    """Gaussian probability density function"""
    return (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

# Step 4: Implement maximum likelihood fitting
def negative_log_likelihood(params):
    """Negative log-likelihood for Gaussian distribution"""
    mu, sigma = params
    if sigma <= 0:
        return np.inf
    return -np.sum(norm.logpdf(data, loc=mu, scale=sigma))

# Initial guess for parameters
initial_params = [np.mean(data), np.std(data)]

# Minimize negative log-likelihood to find MLE estimates
result = minimize(negative_log_likelihood, initial_params, method='Nelder-Mead')
mu_mle, sigma_mle = result.x

print(f"True parameters: mean = {true_mean:.4f}, std = {true_std:.4f}")
print(f"MLE estimates: mean = {mu_mle:.4f}, std = {sigma_mle:.4f}")

# Step 5: Plot histogram and fit curve
x_values = np.linspace(data.min() - 1, data.max() + 1, 1000)
y_fit = gaussian(x_values, mu_mle, sigma_mle)

plt.plot(x_values, y_fit, 'r-', linewidth=2, label=f'Gaussian Fit (μ={mu_mle:.2f}, σ={sigma_mle:.2f})')
plt.xlabel('Value')
plt.ylabel('Probability Density')
plt.title('Gaussian Distribution Fit using Maximum Likelihood Estimation')
plt.legend()
plt.grid(True, alpha=0.3)

# Step 6: Save plot as JPG
plt.savefig('gaussian_fit.jpg', format='jpg', dpi=300, bbox_inches='tight')
print("Plot saved as 'gaussian_fit.jpg'")

plt.show()
