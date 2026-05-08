import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

# Set random seed for reproducibility
np.random.seed(42)

# 1. Generate random Breit-Wigner numbers
# Breit-Wigner (Cauchy) distribution: f(x) = (Γ/2π) / ((x - E₀)² + (Γ/2)²)
def generate_breit_wigner_data(n_samples=1000, E0_true=5.0, gamma_true=2.0):
    """Generate random Breit-Wigner distributed data.
    
    Using the inverse transform method for Cauchy distribution.
    """
    # Generate uniform random numbers
    u = np.random.uniform(0, 1, n_samples)
    # Inverse CDF of Cauchy distribution: x = E0 + (gamma/2) * tan(π(u - 0.5))
    data = E0_true + (gamma_true / 2.0) * np.tan(np.pi * (u - 0.5))
    return data

# 2. Define the Breit-Wigner PDF
def breit_wigner_pdf(x, E0, gamma):
    """Breit-Wigner (Cauchy) probability density function.
    
    f(x) = (Γ/2π) / ((x - E₀)² + (Γ/2)²)
    """
    return (gamma / (2 * np.pi)) / ((x - E0)**2 + (gamma / 2)**2)

# 3. Define the negative log-likelihood function for MLE
def negative_log_likelihood(params, data):
    """Calculate negative log-likelihood for Breit-Wigner distribution."""
    E0, gamma = params
    # Ensure gamma is positive
    if gamma <= 0:
        return np.inf
    # Log-likelihood: sum of log(pdf)
    # Log of Breit-Wigner PDF: log(gamma/2π) - log((x-E0)² + (gamma/2)²)
    log_likelihood = np.sum(np.log(gamma / (2 * np.pi)) - np.log((data - E0)**2 + (gamma / 2)**2))
    return -log_likelihood

# 4. Fit using Maximum Likelihood Estimation
def fit_breit_wigner_mle(data):
    """Fit Breit-Wigner parameters using Maximum Likelihood Estimation."""
    # Initial guess: median for E0, IQR for gamma
    E0_init = np.median(data)
    q75, q25 = np.percentile(data, [75, 25])
    gamma_init = (q75 - q25)  # IQR as initial guess for width
    
    # Minimize negative log-likelihood
    result = minimize(
        negative_log_likelihood,
        x0=[E0_init, gamma_init],
        args=(data,),
        method='Nelder-Mead',
        options={'maxiter': 10000}
    )
    
    E0_fit, gamma_fit = result.x
    return E0_fit, gamma_fit, result.success

# Main execution
if __name__ == "__main__":
    # Parameters for data generation
    n_samples = 10000
    E0_true = 5.0
    gamma_true = 2.0
    
    print("=" * 60)
    print("Breit-Wigner Fit using Maximum Likelihood Estimation")
    print("=" * 60)
    
    # Generate data
    print(f"\n1. Generating {n_samples} random Breit-Wigner numbers...")
    print(f"   True parameters: E0 = {E0_true}, gamma = {gamma_true}")
    data = generate_breit_wigner_data(n_samples, E0_true, gamma_true)
    
    # Filter extreme outliers for better visualization (Cauchy has heavy tails)
    # Keep data within reasonable range for fitting and plotting
    data_filtered = data[(data > E0_true - 10*gamma_true) & (data < E0_true + 10*gamma_true)]
    print(f"   Data range: [{data.min():.2f}, {data.max():.2f}]")
    print(f"   Filtered to {len(data_filtered)} samples for fitting (removed extreme outliers)")
    
    # Fit using MLE
    print("\n2. Fitting using Maximum Likelihood Estimation...")
    E0_fit, gamma_fit, success = fit_breit_wigner_mle(data_filtered)
    
    if success:
        print(f"   Fitted parameters: E0 = {E0_fit:.4f}, gamma = {gamma_fit:.4f}")
        print(f"   Errors: E0_err = {abs(E0_fit - E0_true):.4f}, gamma_err = {abs(gamma_fit - gamma_true):.4f}")
    else:
        print("   Warning: Fitting did not converge!")
    
    # Create histogram and fit curve
    print("\n3. Creating histogram and fit curve...")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot histogram
    n, bins, patches = ax.hist(data_filtered, bins=100, density=True, alpha=0.7, 
                                color='lightcoral', edgecolor='black',
                                label='Histogram (Mass Spectrum)')
    
    # Generate x values for smooth curve
    x_min, x_max = data_filtered.min() - 1, data_filtered.max() + 1
    x_range = np.linspace(x_min, x_max, 1000)
    
    # Plot fitted Breit-Wigner curve
    y_fit = breit_wigner_pdf(x_range, E0_fit, gamma_fit)
    ax.plot(x_range, y_fit, 'r-', linewidth=2, 
            label=f'Fitted Breit-Wigner\nE0 = {E0_fit:.3f}, Γ = {gamma_fit:.3f}')
    
    # Plot true Breit-Wigner curve for comparison
    y_true = breit_wigner_pdf(x_range, E0_true, gamma_true)
    ax.plot(x_range, y_true, 'b--', linewidth=2, alpha=0.7,
            label=f'True Breit-Wigner\nE0 = {E0_true:.3f}, Γ = {gamma_true:.3f}')
    
    # Labels and title
    ax.set_xlabel('Mass (GeV)', fontsize=12)
    ax.set_ylabel('Probability Density', fontsize=12)
    ax.set_title('Breit-Wigner Resonance Fit using Maximum Likelihood Estimation', 
                 fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    
    # Save figure as JPG
    output_file = 'breit_wigner_fit.jpg'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', format='jpg')
    print(f"\n4. Figure saved as '{output_file}'")
    
    plt.tight_layout()
    plt.show()
    
    print("\n" + "=" * 60)
    print("Analysis complete!")
    print("=" * 60)
