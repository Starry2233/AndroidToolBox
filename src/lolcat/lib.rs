mod shared;
use shared::{file_lolcat, string_lolcat};
use pyo3::prelude::*;

#[pyfunction]
fn lolcat_string(s: &str) -> String {
    string_lolcat(s)
}

#[pyfunction]
fn lolcat_file(path: &str) -> PyResult<String> {
    match file_lolcat(path) {
        Ok(output) => Ok(output),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Error: {}", e))),
    }
}

#[pymodule]
fn lolcat_lib(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(lolcat_string, m)?)?;
    m.add_function(wrap_pyfunction!(lolcat_file, m)?)?;
    Ok(())
}
