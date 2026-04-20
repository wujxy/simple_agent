import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from scipy.stats import norm

# Step 1: Generate random Gaussian data
np.random.seed(42)  # For reproducibility
true_mean = 5.0
true_std = 2.0
n_samples = 1000

data = np.random.normal(true_mean, true_std, n_samples)

# Step 2: Define Gaussian fit function (probability density function)
def gaussian_pdf(x, mu, sigma):
    """Gaussian probability density function"""
    return (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

# Step 3: Implement maximum likelihood fitting
def negative_log_likelihood(params, data):
    """Negative log-likelihood function for Gaussian distribution"""
    mu, sigma = params
    # Avoid invalid sigma values
    if sigma <= 0:
        return np.inf
    # Log-likelihood for Gaussian distribution
    log_likelihood = np.sum(norm.logpdf(data, loc=mu, scale=sigma))
    return -log_likelihood

# Initial guess for parameters
initial_params = [np.mean(data), np.std(data)]

# Minimize negative log-likelihood to find MLE estimates
result = minimize(negative_log_likelihood, initial_params, args=(data,))
mle_mean, mle_std = result.x

print(f"True parameters: mean = {true_mean:.4f}, std = {true_std:.4f}")
print(f"MLE estimates: mean = {mle_mean:.4f}, std = {mle_std:.4f}")

# Step 4: Create histogram and fit curve plot
plt.figure(figsize=(10, 6))

# Plot histogram
n, bins, patches = plt.hist(data, bins=50, density=True, alpha=0.6, color='skyblue', edgecolor='black', label='Histogram')

# Generate x values for smooth curve
x_smooth = np.linspace(data.min() - 1, data.max() + 1, 1000)

# Plot fitted Gaussian curve using MLE parameters
y_fit = gaussian_pdf(x_smooth, mle_mean, mle_std)
plt.plot(x_smooth, y_fit, 'r-', linewidth=2, label=f'Gaussian Fit (μ={mle_mean:.2f}, σ={mle_std:.2f})')

# Add labels and title
plt.xlabel('Value', fontsize=12)
plt.ylabel('Probability Density', fontsize=12)
plt.title('Gaussian Fit using Maximum Likelihood Estimation', fontsize=14)
plt.legend(fontsize=10)
plt.grid(True, alpha=0.3)

# Step 5: Save plot as JPG file
plt.savefig('gaussian_fit.jpg', format='jpg', dpi=300, bbox_inches='tight')
print("Plot saved as 'gaussian_fit.jpg'")

plt.show()
