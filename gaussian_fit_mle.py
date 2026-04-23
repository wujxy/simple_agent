import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from scipy.stats import norm

# Set random seed for reproducibility
np.random.seed(42)

# 1. Generate random Gaussian numbers
def generate_gaussian_data(n_samples=1000, mu_true=5.0, sigma_true=2.0):
    """Generate random Gaussian distributed data."""
    return np.random.normal(loc=mu_true, scale=sigma_true, size=n_samples)

# 2. Define the negative log-likelihood function for MLE
def negative_log_likelihood(params, data):
    """Calculate negative log-likelihood for Gaussian distribution."""
    mu, sigma = params
    # Ensure sigma is positive
    if sigma <= 0:
        return np.inf
    # Log-likelihood for Gaussian: sum of log(pdf)
    log_likelihood = np.sum(norm.logpdf(data, loc=mu, scale=sigma))
    return -log_likelihood

# 3. Fit using Maximum Likelihood Estimation
def fit_gaussian_mle(data):
    """Fit Gaussian parameters using Maximum Likelihood Estimation."""
    # Initial guess: sample mean and standard deviation
    mu_init = np.mean(data)
    sigma_init = np.std(data)
    
    # Minimize negative log-likelihood
    result = minimize(
        negative_log_likelihood,
        x0=[mu_init, sigma_init],
        args=(data,),
        method='Nelder-Mead',
        options={'maxiter': 1000}
    )
    
    mu_fit, sigma_fit = result.x
    return mu_fit, sigma_fit, result.success

# 4. Gaussian PDF function for plotting
def gaussian_pdf(x, mu, sigma):
    """Gaussian probability density function."""
    return (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

# Main execution
if __name__ == "__main__":
    # Parameters for data generation
    n_samples = 1000
    mu_true = 5.0
    sigma_true = 2.0
    
    print("=" * 50)
    print("Gaussian Fit using Maximum Likelihood Estimation")
    print("=" * 50)
    
    # Generate data
    print(f"\n1. Generating {n_samples} random Gaussian numbers...")
    print(f"   True parameters: mu = {mu_true}, sigma = {sigma_true}")
    data = generate_gaussian_data(n_samples, mu_true, sigma_true)
    
    # Fit using MLE
    print("\n2. Fitting using Maximum Likelihood Estimation...")
    mu_fit, sigma_fit, success = fit_gaussian_mle(data)
    
    if success:
        print(f"   Fitted parameters: mu = {mu_fit:.4f}, sigma = {sigma_fit:.4f}")
        print(f"   Errors: mu_err = {abs(mu_fit - mu_true):.4f}, sigma_err = {abs(sigma_fit - sigma_true):.4f}")
    else:
        print("   Warning: Fitting did not converge!")
    
    # Create histogram and fit curve
    print("\n3. Creating histogram and fit curve...")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot histogram
    n, bins, patches = ax.hist(data, bins=50, density=True, alpha=0.7, 
                                color='skyblue', edgecolor='black',
                                label='Histogram')
    
    # Generate x values for smooth curve
    x_range = np.linspace(data.min() - 1, data.max() + 1, 500)
    
    # Plot fitted Gaussian curve
    y_fit = gaussian_pdf(x_range, mu_fit, sigma_fit)
    ax.plot(x_range, y_fit, 'r-', linewidth=2, 
            label=f'Fit: $\mu$={mu_fit:.2f}, $\sigma$={sigma_fit:.2f}')
    
    # Plot true Gaussian curve for comparison
    y_true = gaussian_pdf(x_range, mu_true, sigma_true)
    ax.plot(x_range, y_true, 'g--', linewidth=2, alpha=0.7,
            label=f'True: $\mu$={mu_true:.2f}, $\sigma$={sigma_true:.2f}')
    
    # Formatting
    ax.set_xlabel('Value', fontsize=12)
    ax.set_ylabel('Probability Density', fontsize=12)
    ax.set_title('Gaussian Distribution Fit using Maximum Likelihood Estimation', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    
    # Save as JPG
    output_file = 'gaussian_fit.jpg'
    plt.savefig(output_file, format='jpg', dpi=300, bbox_inches='tight')
    print(f"\n4. Plot saved as '{output_file}'")
    
    plt.tight_layout()
    plt.show()
    
    print("\n" + "=" * 50)
    print("Program completed successfully!")
    print("=" * 50)
