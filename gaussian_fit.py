import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from scipy.stats import norm

# Set random seed for reproducibility
np.random.seed(42)

# Parameters for the true Gaussian distribution
true_mean = 5.0
true_std = 2.0
n_samples = 1000

# Step 1: Generate random Gaussian data
def generate_gaussian_data(mean, std, n_samples):
    """Generate random numbers following a Gaussian distribution."""
    return np.random.normal(loc=mean, scale=std, size=n_samples)

# Generate the data
data = generate_gaussian_data(true_mean, true_std, n_samples)
print(f"Generated {n_samples} samples from Gaussian distribution")
print(f"True parameters: mean = {true_mean}, std = {true_std}")

# Step 2: Define Gaussian fit function
def gaussian_pdf(x, mean, std):
    """Gaussian probability density function."""
    return (1.0 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)

# Step 3: Implement maximum likelihood fitting
def negative_log_likelihood(params, data):
    """Negative log-likelihood function for Gaussian distribution."""
    mean, std = params
    # Ensure std is positive
    if std <= 0:
        return np.inf
    # Log-likelihood for Gaussian: sum of log(pdf)
    log_likelihood = np.sum(norm.logpdf(data, loc=mean, scale=std))
    return -log_likelihood

def maximum_likelihood_fit(data):
    """Fit Gaussian parameters using maximum likelihood estimation."""
    # Initial guess: sample mean and sample standard deviation
    initial_guess = [np.mean(data), np.std(data)]
    
    # Optimize to minimize negative log-likelihood
    result = minimize(negative_log_likelihood, initial_guess, args=(data,),
                      method='Nelder-Mead')
    
    fitted_mean, fitted_std = result.x
    return fitted_mean, fitted_std, result.success

# Perform the fit
fitted_mean, fitted_std, success = maximum_likelihood_fit(data)
print(f"\nFitted parameters: mean = {fitted_mean:.4f}, std = {fitted_std:.4f}")
print(f"Fit successful: {success}")

# Step 4: Create histogram and fit curve plot
plt.figure(figsize=(10, 6))

# Plot histogram of the data
hist_counts, hist_bins, hist_patches = plt.hist(data, bins=50, density=True, 
                                                 alpha=0.6, color='skyblue', 
                                                 edgecolor='black',
                                                 label='Histogram')

# Generate x values for the smooth fit curve
x_fit = np.linspace(data.min() - 1, data.max() + 1, 500)

# Plot the fitted Gaussian curve
y_fit = gaussian_pdf(x_fit, fitted_mean, fitted_std)
plt.plot(x_fit, y_fit, 'r-', linewidth=2, label=f'Gaussian Fit\n$\mu$={fitted_mean:.2f}, $\sigma$={fitted_std:.2f}')

# Plot the true Gaussian curve for comparison
y_true = gaussian_pdf(x_fit, true_mean, true_std)
plt.plot(x_fit, y_true, 'g--', linewidth=2, alpha=0.7, label=f'True Gaussian\n$\mu$={true_mean}, $\sigma$={true_std}')

# Add labels and title
plt.xlabel('Value', fontsize=12)
plt.ylabel('Probability Density', fontsize=12)
plt.title('Gaussian Distribution Fitting using Maximum Likelihood Estimation', fontsize=14)
plt.legend(fontsize=10)
plt.grid(True, alpha=0.3)

# Step 5: Save plot as JPG file
plt.tight_layout()
plt.savefig('gaussian_fit.jpg', format='jpg', dpi=300, bbox_inches='tight')
print("\nPlot saved as 'gaussian_fit.jpg'")

plt.show()

# Print summary
print("\n" + "="*50)
print("SUMMARY")
print("="*50)
print(f"True mean: {true_mean:.4f}, Fitted mean: {fitted_mean:.4f}, Error: {abs(true_mean - fitted_mean):.4f}")
print(f"True std:  {true_std:.4f}, Fitted std:  {fitted_std:.4f}, Error: {abs(true_std - fitted_std):.4f}")
