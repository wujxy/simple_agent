import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from scipy.stats import norm

# Step 1: Generate random Gaussian data
np.random.seed(42)
true_mean = 5.0
true_std = 2.0
n_samples = 1000
data = np.random.normal(true_mean, true_std, n_samples)

# Step 2: Create histogram of generated data
hist_counts, bin_edges, _ = plt.hist(data, bins=30, density=True, alpha=0.6, color='g', label='Histogram')

# Step 3: Define Gaussian fit function (probability density function)
def gaussian_pdf(x, mu, sigma):
    """Gaussian probability density function"""
    return (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

# Step 4: Implement maximum likelihood fitting
def negative_log_likelihood(params, data):
    """Negative log-likelihood for Gaussian distribution"""
    mu, sigma = params
    if sigma <= 0:
        return np.inf  # Prevent negative or zero standard deviation
    n = len(data)
    log_likelihood = -n * np.log(sigma) - 0.5 * n * np.log(2 * np.pi) - 0.5 * np.sum(((data - mu) / sigma) ** 2)
    return -log_likelihood  # Return negative for minimization

# Initial guess for parameters
initial_params = [np.mean(data), np.std(data)]

# Minimize negative log-likelihood to find MLE estimates
result = minimize(negative_log_likelihood, initial_params, args=(data,))
mle_mean, mle_std = result.x

print(f"True parameters: mean = {true_mean:.4f}, std = {true_std:.4f}")
print(f"MLE estimates: mean = {mle_mean:.4f}, std = {mle_std:.4f}")

# Step 5: Plot histogram and fit curve
x_values = np.linspace(data.min() - 1, data.max() + 1, 1000)
fit_curve = gaussian_pdf(x_values, mle_mean, mle_std)

plt.plot(x_values, fit_curve, 'r-', linewidth=2, label=f'Gaussian Fit (μ={mle_mean:.2f}, σ={mle_std:.2f})')
plt.xlabel('Value')
plt.ylabel('Probability Density')
plt.title('Gaussian Distribution Fit using Maximum Likelihood Estimation')
plt.legend()
plt.grid(True, alpha=0.3)

# Step 6: Save plot as JPG file
plt.savefig('gaussian_fit.jpg', format='jpg', dpi=300, bbox_inches='tight')
print("Plot saved as 'gaussian_fit.jpg'")

plt.show()
