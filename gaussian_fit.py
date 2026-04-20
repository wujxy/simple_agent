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

print(f"Generated {n_samples} samples from Gaussian distribution")
print(f"True mean: {true_mean}, True std: {true_std}")

# Step 2: Define the Gaussian function (PDF)
def gaussian_pdf(x, mu, sigma):
    """Gaussian probability density function"""
    return (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

# Step 3: Maximum Likelihood Estimation (MLE)
def negative_log_likelihood(params, data):
    """Negative log-likelihood for Gaussian distribution"""
    mu, sigma = params
    # Avoid invalid sigma values
    if sigma <= 0:
        return np.inf
    # Log-likelihood for Gaussian: sum of log(pdf)
    log_likelihood = np.sum(norm.logpdf(data, loc=mu, scale=sigma))
    return -log_likelihood

# Initial guess for parameters
initial_params = [np.mean(data), np.std(data)]

# Minimize the negative log-likelihood
result = minimize(negative_log_likelihood, initial_params, args=(data,))

fitted_mean, fitted_std = result.x
print(f"\nFitted parameters (MLE):")
print(f"Mean: {fitted_mean:.4f}")
print(f"Std: {fitted_std:.4f}")

# Step 4: Plot histogram and fitted curve
plt.figure(figsize=(10, 6))

# Create histogram
n, bins, patches = plt.hist(data, bins=30, density=True, alpha=0.6, color='skyblue', edgecolor='black', label='Histogram')

# Generate points for the fitted curve
x_range = np.linspace(data.min() - 1, data.max() + 1, 1000)
y_fitted = gaussian_pdf(x_range, fitted_mean, fitted_std)

# Plot the fitted curve
plt.plot(x_range, y_fitted, 'r-', linewidth=2, label=f'Gaussian Fit (μ={fitted_mean:.2f}, σ={fitted_std:.2f})')

# Add labels and title
plt.xlabel('Value', fontsize=12)
plt.ylabel('Probability Density', fontsize=12)
plt.title('Gaussian Distribution Fit using Maximum Likelihood Estimation', fontsize=14)
plt.legend(fontsize=10)
plt.grid(True, alpha=0.3)

# Step 5: Save plot as JPG file
plt.savefig('gaussian_fit.jpg', format='jpg', dpi=300, bbox_inches='tight')
print("\nPlot saved as 'gaussian_fit.jpg'")

# Display the plot
plt.show()
