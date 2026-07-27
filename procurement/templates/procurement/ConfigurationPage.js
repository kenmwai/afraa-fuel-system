import React, { useState, useEffect } from 'react';
import axios from 'axios';

const ConfigurationPage = () => {
    const [currencies, setCurrencies] = useState([]);
    const [units, setUnits] = useState([]);
    const [creditRate, setCreditRate] = useState(0);

    useEffect(() => {
        // Fetch all config data from API
        fetchData();
    }, []);

    const fetchData = async () => {
        const res = await axios.get('http://127.0.0.1:8000/api/config/all/');
        setCurrencies(res.data.currencies);
        setUnits(res.data.units);
        setCreditRate(res.data.credit_rate);
    };

    const handleAddCurrency = async (e) => {
        e.preventDefault();
        const form = e.target;
        await axios.post('http://127.0.0.1:8000/api/config/currency/', {
            code: form.code.value,
            exchange_rate_to_usd: form.rate.value
        });
        fetchData();
    };

    return (
        <div className="p-8 bg-gray-50 min-h-screen">
            <h1 className="text-3xl font-bold mb-8">System Configuration</h1>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Currency Management */}
                <div className="bg-white p-6 rounded-xl shadow-sm border">
                    <h2 className="text-xl font-bold mb-4">Currencies & Exchange Rates</h2>
                    <form onSubmit={handleAddCurrency} className="flex gap-2 mb-4">
                        <input name="code" placeholder="USD" className="border p-2 rounded w-20" required />
                        <input name="rate" placeholder="Rate to USD" type="number" step="0.000001" className="border p-2 rounded flex-1" required />
                        <button className="bg-blue-600 text-white px-4 py-2 rounded">Add</button>
                    </form>
                    <table className="w-full text-sm">
                        <thead className="bg-gray-100">
                            <tr><th className="p-2 text-left">Code</th><th className="p-2 text-right">Rate to 1 USD</th></tr>
                        </thead>
                        <tbody>
                            {currencies.map(c => (
                                <tr key={c.code} className="border-b">
                                    <td className="p-2">{c.code}</td>
                                    <td className="p-2 text-right">{c.exchange_rate_to_usd}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Global Factors */}
                <div className="bg-white p-6 rounded-xl shadow-sm border">
                    <h2 className="text-xl font-bold mb-4">Financial Factors</h2>
                    <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700">Annual Cost of Credit (%)</label>
                        <div className="flex gap-2 mt-1">
                            <input 
                                type="number" 
                                value={creditRate * 100} 
                                onChange={(e) => setCreditRate(e.target.value / 100)}
                                className="border p-2 rounded w-full"
                            />
                            <button className="bg-green-600 text-white px-4 py-2 rounded">Update</button>
                        </div>
                        <p className="text-xs text-gray-500 mt-2">This rate is used to calculate the financial benefit of supplier credit terms.</p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ConfigurationPage;