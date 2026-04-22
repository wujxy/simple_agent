import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

# Parameters for the Gaussian distribution
true_mean = 5.0
true_std = 2.0
n_samples = 10000

# Generate random Gaussian numbers
np.random.seed(42)  # For reproducibility
data = np.random.normal(loc=true_mean, scale=true_std, size=n_samples)

# Maximum likelihood estimation
# For Gaussian, MLE of mean = sample mean, MLE of std = sample std (with n denominator)
mle_mean = np.mean(data)
mle_std = np.sqrt(np.mean((data - mle_mean) ** 2))

print(f"True parameters: mean = {true_mean:.4f}, std = {true_std:.4f}")
print(f"MLE estimates:   mean = {mle_mean:.4f}, std = {mle_std:.4f}")

# Create histogram and fit curve
fig, ax = plt.subplots(figsize=(10, 6))

# Plot histogram
n, bins, patches = ax.hist(data, bins=50, density=True, alpha=0.7, 
                           color='skyblue', edgecolor='black', 
                           label='Histogram')

# Generate x values for the fitted curve
x = np.linspace(data.min(), data.max(), 1000)

# Plot the fitted Gaussian curve (using MLE parameters)
fitted_pdf = norm.pdf(x, loc=mle_mean, scale=mle_std)
ax.plot(x, fitted_pdf, 'r-', linewidth=2, 
        label=f'Gaussian Fit (μ={mle_mean:.2f}, σ={mle_std:.2f})')

# Also plot the true Gaussian for comparison
true_pdf = norm.pdf(x, loc=true_mean, scale=true_std)
ax.plot(x, true_pdf, 'g--', linewidth=2, alpha=0.7,
        label=f'True Gaussian (μ={true_mean:.2f}, σ={true_std:.2f})')

# Add labels and legend
ax.set_xlabel('Value', fontsize=12)
ax.set_ylabel('Probability Density', fontsize=12)
ax.set_title('Gaussian Distribution: Histogram with Maximum Likelihood Fit', fontsize=14)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)

# Save as JPG
plt.tight_layout()
plt.savefig('gaussian_fit.jpg', format='jpg', dpi=300, bbox_inches='tight')
print("\nPlot saved as 'gaussian_fit.jpg'")

# Show the plot
plt.show()
